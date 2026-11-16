#include "analytics.hpp"

#include <algorithm>
#include <chrono>
#include <climits>
#include <exception>
#include <iostream>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#ifdef TAXI_HAS_OPENMP
#include <omp.h>
#endif

namespace {

struct Options {
    std::filesystem::path input = "data/processed/taxi_2025_clean.csv";
    std::filesystem::path output = "results/openmp.csv";
    int threads = 1;
    std::string schedule = "static";
    int chunk = 0;               // 0 = OpenMP default chunk for the schedule
    std::string strategy = "local";
    int parse_tasks = 0;         // 0 = 8 tasks per thread
};

Options parse_args(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (i + 1 >= argc) throw std::runtime_error("Missing value for " + arg);
        const std::string val = argv[++i];
        if (arg == "--input") o.input = val;
        else if (arg == "--output") o.output = val;
        else if (arg == "--threads") o.threads = std::stoi(val);
        else if (arg == "--schedule") o.schedule = val;
        else if (arg == "--chunk") o.chunk = std::stoi(val);
        else if (arg == "--strategy") o.strategy = val;
        else if (arg == "--parse-tasks") o.parse_tasks = std::stoi(val);
        else throw std::runtime_error("Unknown option: " + arg);
    }
    if (o.threads < 1 || o.threads > 256) throw std::runtime_error("--threads must be between 1 and 256");
    if (o.schedule != "static" && o.schedule != "dynamic" && o.schedule != "guided")
        throw std::runtime_error("--schedule must be static, dynamic, or guided");
    if (o.chunk < 0) throw std::runtime_error("--chunk must be >= 0");
    if (o.parse_tasks < 0) throw std::runtime_error("--parse-tasks must be >= 0");
    const std::string s = o.strategy;
    if (s != "local" && s != "reduction" && s != "atomic" && s != "critical" && s != "map")
        throw std::runtime_error("--strategy must be local, reduction, atomic, critical, or map");
#ifndef TAXI_HAS_OPENMP
    if (o.threads > 1) throw std::runtime_error("This build has no OpenMP support; install an OpenMP-capable compiler and reconfigure CMake");
#endif
    return o;
}

#ifdef TAXI_HAS_OPENMP

// Parsed trips live in one array allocated with new[]: Trip is trivial, so
// nothing is zero-filled and each task touches its own pages first.
struct TripBuffer {
    std::unique_ptr<taxi::Trip[]> data;
    std::size_t size = 0;
    std::span<const taxi::Trip> view() const { return {data.get(), size}; }
};

// Split the body into roughly equal pieces that start right after a newline.
// Pass 1 counts lines per piece (parallel for), pass 2 parses every piece in
// its own task straight into its slice of the output array.
TripBuffer parse_parallel(std::string_view body, int tasks) {
    std::vector<std::size_t> cuts{0};
    for (int k = 1; k < tasks; ++k) {
        const std::size_t pos = body.size() * static_cast<std::size_t>(k) / static_cast<std::size_t>(tasks);
        if (pos <= cuts.back()) continue;
        const auto nl = body.find('\n', pos - 1);
        if (nl == std::string_view::npos) break;
        if (nl + 1 > cuts.back() && nl + 1 < body.size()) cuts.push_back(nl + 1);
    }
    cuts.push_back(body.size());
    const auto n = static_cast<std::int64_t>(cuts.size() - 1);
    auto piece = [&](std::int64_t k) {
        const auto i = static_cast<std::size_t>(k);
        return body.substr(cuts[i], cuts[i + 1] - cuts[i]);
    };

    std::vector<std::size_t> lines(static_cast<std::size_t>(n));
#pragma omp parallel for schedule(static)
    for (std::int64_t k = 0; k < n; ++k) lines[static_cast<std::size_t>(k)] = taxi::line_count(piece(k));
    std::vector<std::size_t> offset(static_cast<std::size_t>(n) + 1, 0);
    for (std::size_t k = 0; k < lines.size(); ++k) offset[k + 1] = offset[k] + lines[k];

    TripBuffer buf;
    buf.data.reset(new taxi::Trip[offset.back() + 1]);
    taxi::Trip* out = buf.data.get();
    std::vector<std::size_t> written(static_cast<std::size_t>(n), 0);
    std::vector<std::exception_ptr> errors(static_cast<std::size_t>(n));
#pragma omp parallel
#pragma omp single
    for (std::int64_t k = 0; k < n; ++k) {
#pragma omp task firstprivate(k)
        {
            const auto i = static_cast<std::size_t>(k);
            try {
                written[i] = taxi::parse_into(piece(k), out + offset[i], 0);
            } catch (...) {
                errors[i] = std::current_exception();
            }
        }
    }
    for (const auto& e : errors)
        if (e) {
            // Re-parse serially so the error message has the real line number.
            std::vector<taxi::Trip> scratch;
            taxi::parse_range(body, scratch, 2);
            std::rethrow_exception(e);
        }

    // Empty lines leave gaps; close them (only happens with hand-made input).
    std::size_t size = 0;
    for (std::size_t k = 0; k < written.size(); ++k) {
        if (size != offset[k]) std::copy(out + offset[k], out + offset[k] + written[k], out + size);
        size += written[k];
    }
    buf.size = size;
    return buf;
}

taxi::Results aggregate_map_local(std::span<const taxi::Trip> trips) {
    taxi::Results results;
    const auto n = static_cast<std::int64_t>(trips.size());
#pragma omp parallel
    {
        taxi::Results mine;
#pragma omp for schedule(runtime) nowait
        for (std::int64_t i = 0; i < n; ++i) {
            const auto& t = trips[static_cast<std::size_t>(i)];
            mine[{t.pickup_zone, t.hour}].add(t.distance);
        }
#pragma omp critical(merge_maps)
        taxi::merge(results, mine);
    }
    return results;
}

taxi::Results aggregate_parallel(std::span<const taxi::Trip> trips, const std::string& strategy) {
    if (trips.empty()) return {};
    const auto n = static_cast<std::int64_t>(trips.size());

    int lo = INT_MAX, hi = INT_MIN;
#pragma omp parallel for schedule(static) reduction(min : lo) reduction(max : hi)
    for (std::int64_t i = 0; i < n; ++i) {
        const int z = trips[static_cast<std::size_t>(i)].pickup_zone;
        lo = std::min(lo, z);
        hi = std::max(hi, z);
    }
    const auto span = static_cast<long long>(hi) - lo + 1;
    if (strategy == "map" || static_cast<std::size_t>(span) * taxi::kHours > taxi::kMaxDenseBins)
        return aggregate_map_local(trips);

    taxi::DenseTable total(lo, hi);
    std::uint64_t* cnt = total.counts.data();
    double* sum = total.sums.data();
    const auto bins = total.bins();
    const int base = lo;

    if (strategy == "local") {
#pragma omp parallel
        {
            taxi::DenseTable mine(lo, hi);
#pragma omp for schedule(runtime) nowait
            for (std::int64_t i = 0; i < n; ++i) mine.add(trips[static_cast<std::size_t>(i)]);
            // One merge per thread, so a critical section is cheap here.
#pragma omp critical(merge_tables)
            total.merge(mine);
        }
    } else if (strategy == "reduction") {
#pragma omp parallel for schedule(runtime) reduction(+ : cnt[:bins], sum[:bins])
        for (std::int64_t i = 0; i < n; ++i) {
            const auto& t = trips[static_cast<std::size_t>(i)];
            const auto b = static_cast<std::size_t>(t.pickup_zone - base) * taxi::kHours + static_cast<std::size_t>(t.hour);
            cnt[b] += 1;
            sum[b] += t.distance;
        }
    } else if (strategy == "atomic") {
#pragma omp parallel for schedule(runtime)
        for (std::int64_t i = 0; i < n; ++i) {
            const auto& t = trips[static_cast<std::size_t>(i)];
            const auto b = static_cast<std::size_t>(t.pickup_zone - base) * taxi::kHours + static_cast<std::size_t>(t.hour);
#pragma omp atomic
            cnt[b] += 1;
#pragma omp atomic
            sum[b] += t.distance;
        }
    } else {  // critical
#pragma omp parallel for schedule(runtime)
        for (std::int64_t i = 0; i < n; ++i) {
            const auto& t = trips[static_cast<std::size_t>(i)];
            const auto b = static_cast<std::size_t>(t.pickup_zone - base) * taxi::kHours + static_cast<std::size_t>(t.hour);
#pragma omp critical(table_update)
            {
                cnt[b] += 1;
                sum[b] += t.distance;
            }
        }
    }
    return total.to_results();
}
#endif

}  // namespace

int main(int argc, char** argv) try {
    const Options opt = parse_args(argc, argv);
    using clock = std::chrono::steady_clock;

    const auto start = clock::now();
    std::size_t offset = 0;
    const std::string text = taxi::read_file(opt.input, offset);
    const std::string_view body = std::string_view(text).substr(offset);
    const auto read_done = clock::now();

    taxi::Results results;
    std::size_t records = 0;
#ifdef TAXI_HAS_OPENMP
    omp_set_num_threads(opt.threads);
    const omp_sched_t kind = opt.schedule == "dynamic" ? omp_sched_dynamic
                           : opt.schedule == "guided"  ? omp_sched_guided
                                                       : omp_sched_static;
    omp_set_schedule(kind, opt.chunk);
    const int tasks = opt.parse_tasks ? opt.parse_tasks : 8 * opt.threads;
    const TripBuffer trips = parse_parallel(body, tasks);
    records = trips.size;
    const auto loaded = clock::now();
    results = aggregate_parallel(trips.view(), opt.strategy);
#else
    std::vector<taxi::Trip> trips;
    trips.reserve(body.size() / 20 + 1);
    taxi::parse_range(body, trips, 2);
    records = trips.size();
    const auto loaded = clock::now();
    results = opt.strategy == "map" ? taxi::aggregate_map(trips) : taxi::aggregate_serial(trips);
#endif
    const auto aggregated = clock::now();
    taxi::write_results(opt.output, results);
    const auto written = clock::now();

    const auto ms = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
    std::cout << "records=" << records << "\ngroups=" << results.size() << "\nthreads=" << opt.threads
              << "\nschedule=" << opt.schedule << "\nchunk=" << opt.chunk << "\nstrategy=" << opt.strategy
              << "\nread_ms=" << ms(start, read_done) << "\nparse_ms=" << ms(read_done, loaded)
              << "\nloading_ms=" << ms(start, loaded) << "\naggregation_ms=" << ms(loaded, aggregated)
              << "\nwriting_ms=" << ms(aggregated, written) << "\nend_to_end_ms=" << ms(start, written) << '\n';
    return 0;
} catch (const std::exception& e) {
    std::cerr << "openmp: " << e.what() << '\n';
    return 2;
}
