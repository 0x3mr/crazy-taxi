// False sharing check (Lab 5 style).
// Each thread counts its "long trips" (distance > --threshold miles) in a
// per-thread counter. Three versions:
//   adjacent - counters packed in one array, so several share a cache line
//   padded   - each counter on its own 64-byte line
//   private  - a local variable combined with reduction(+)
// The counters are written through a volatile pointer so the compiler keeps
// every update in memory, which is what a naive shared-counter version does.
#include "analytics.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <omp.h>

namespace {
struct alignas(64) PaddedCounter {
    std::uint64_t value = 0;
};

template <typename F>
double time_ms(F&& f) {
    const auto t0 = std::chrono::steady_clock::now();
    f();
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
}
}  // namespace

int main(int argc, char** argv) try {
    std::filesystem::path input;
    std::size_t synthetic = 20'000'000;
    double threshold = 2.0;
    std::vector<int> thread_counts{1, 2, 4, 8};
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (i + 1 >= argc) throw std::runtime_error("Missing value for " + a);
        const std::string v = argv[++i];
        if (a == "--input") input = v;
        else if (a == "--synthetic") synthetic = std::stoull(v);
        else if (a == "--threshold") threshold = std::stod(v);
        else if (a == "--threads") {
            thread_counts.clear();
            std::size_t pos = 0;
            while (pos <= v.size()) {
                const auto comma = v.find(',', pos);
                thread_counts.push_back(std::stoi(v.substr(pos, comma - pos)));
                if (comma == std::string::npos) break;
                pos = comma + 1;
            }
        } else throw std::runtime_error("Unknown option: " + a);
    }

    std::vector<double> d;
    if (!input.empty()) {
        for (const auto& t : taxi::load_csv(input)) d.push_back(t.distance);
    } else {
        d.resize(synthetic);
        for (std::size_t i = 0; i < d.size(); ++i) d[i] = static_cast<double>((i * 37) % 1000) / 100.0;
    }
    const auto n = static_cast<std::int64_t>(d.size());

    for (int threads : thread_counts) {
        if (threads < 1) throw std::runtime_error("thread counts must be positive");
        omp_set_num_threads(threads);

        std::vector<std::uint64_t> adjacent(static_cast<std::size_t>(threads), 0);
        const double adjacent_ms = time_ms([&] {
#pragma omp parallel
            {
                volatile std::uint64_t* mine = &adjacent[static_cast<std::size_t>(omp_get_thread_num())];
#pragma omp for schedule(static)
                for (std::int64_t i = 0; i < n; ++i)
                    if (d[static_cast<std::size_t>(i)] > threshold) *mine = *mine + 1;
            }
        });

        std::vector<PaddedCounter> padded(static_cast<std::size_t>(threads));
        const double padded_ms = time_ms([&] {
#pragma omp parallel
            {
                volatile std::uint64_t* mine = &padded[static_cast<std::size_t>(omp_get_thread_num())].value;
#pragma omp for schedule(static)
                for (std::int64_t i = 0; i < n; ++i)
                    if (d[static_cast<std::size_t>(i)] > threshold) *mine = *mine + 1;
            }
        });

        std::uint64_t reduced = 0;
        const double private_ms = time_ms([&] {
#pragma omp parallel for schedule(static) reduction(+ : reduced)
            for (std::int64_t i = 0; i < n; ++i)
                if (d[static_cast<std::size_t>(i)] > threshold) ++reduced;
        });

        std::uint64_t a = 0, p = 0;
        for (auto v : adjacent) a += v;
        for (const auto& v : padded) p += v.value;
        if (a != reduced || p != reduced) throw std::runtime_error("counter mismatch");
        std::cout << "threads=" << threads << " elements=" << n << " long_trips=" << reduced
                  << " adjacent_ms=" << adjacent_ms << " padded_ms=" << padded_ms << " private_ms=" << private_ms << '\n';
    }
    return 0;
} catch (const std::exception& e) {
    std::cerr << "false_sharing: " << e.what() << '\n';
    return 2;
}
