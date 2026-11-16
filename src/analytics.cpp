#include "analytics.hpp"

#include <charconv>
#include <cmath>
#include <algorithm>
#include <fstream>
#include <iomanip>
#include <stdexcept>

namespace taxi {

bool valid(const Trip& t) noexcept {
    return t.hour >= 0 && t.hour <= 23 && std::isfinite(t.distance) && t.distance > 0.0;
}

namespace {
template <typename T>
T parse_field(std::string_view text, const char* name) {
    T value{};
    const char* first = text.data();
    const char* last = text.data() + text.size();
    const auto [ptr, ec] = std::from_chars(first, last, value);
    if (text.empty() || ec != std::errc{} || ptr != last)
        throw std::invalid_argument(std::string("bad ") + name + " '" + std::string(text) + "'");
    return value;
}
}  // namespace

Trip parse_line(std::string_view line) {
    const auto c1 = line.find(',');
    if (c1 == std::string_view::npos) throw std::invalid_argument("expected 3 fields");
    const auto c2 = line.find(',', c1 + 1);
    if (c2 == std::string_view::npos) throw std::invalid_argument("expected 3 fields");
    if (line.find(',', c2 + 1) != std::string_view::npos) throw std::invalid_argument("too many fields");
    Trip t{parse_field<int>(line.substr(0, c1), "zone"),
           parse_field<int>(line.substr(c1 + 1, c2 - c1 - 1), "hour"),
           parse_field<double>(line.substr(c2 + 1), "distance")};
    if (!valid(t)) throw std::invalid_argument("invalid value");
    return t;
}

std::string read_file(const std::filesystem::path& path, std::size_t& body_offset) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot open input CSV: " + path.string());
    input.seekg(0, std::ios::end);
    const auto size = static_cast<std::size_t>(input.tellg());
    input.seekg(0, std::ios::beg);
    std::string text(size, '\0');
    if (size && !input.read(text.data(), static_cast<std::streamsize>(size)))
        throw std::runtime_error("Error reading input CSV: " + path.string());
    if (text.empty()) throw std::runtime_error("Input CSV is empty");

    auto nl = text.find('\n');
    std::string_view header(text.data(), nl == std::string::npos ? text.size() : nl);
    if (!header.empty() && header.back() == '\r') header.remove_suffix(1);
    if (header != kInputHeader)
        throw std::runtime_error(std::string("Unexpected CSV header; expected ") + kInputHeader);
    body_offset = nl == std::string::npos ? text.size() : nl + 1;
    return text;
}

namespace {
// Parses every non-empty line (LF or CRLF endings) and passes the trip to f.
template <typename F>
void for_each_line(std::string_view text, std::size_t first_line, F&& f) {
    std::size_t line_number = first_line;
    std::size_t pos = 0;
    while (pos < text.size()) {
        auto nl = text.find('\n', pos);
        if (nl == std::string_view::npos) nl = text.size();
        std::string_view line = text.substr(pos, nl - pos);
        if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
        if (!line.empty()) {
            try {
                f(parse_line(line));
            } catch (const std::exception& e) {
                throw std::runtime_error("Invalid CSV record at line " + std::to_string(line_number) + ": " + e.what());
            }
        }
        pos = nl + 1;
        ++line_number;
    }
}
}  // namespace

void parse_range(std::string_view text, std::vector<Trip>& out, std::size_t first_line) {
    for_each_line(text, first_line, [&](const Trip& t) { out.push_back(t); });
}

std::size_t parse_into(std::string_view text, Trip* out, std::size_t first_line) {
    std::size_t n = 0;
    for_each_line(text, first_line, [&](const Trip& t) { out[n++] = t; });
    return n;
}

std::size_t line_count(std::string_view text) noexcept {
    const auto newlines = static_cast<std::size_t>(std::count(text.begin(), text.end(), '\n'));
    return newlines + (!text.empty() && text.back() != '\n' ? 1 : 0);
}

std::vector<Trip> load_csv(const std::filesystem::path& path) {
    std::size_t offset = 0;
    const std::string text = read_file(path, offset);
    std::vector<Trip> trips;
    // ~22 bytes per row in the cleaned file; reserving avoids repeated reallocation.
    trips.reserve((text.size() - offset) / 20 + 1);
    parse_range(std::string_view(text).substr(offset), trips, 2);
    return trips;
}

DenseTable::DenseTable(int lo, int hi)
    : min_zone(lo), zones(hi - lo + 1),
      counts(static_cast<std::size_t>(hi - lo + 1) * kHours, 0),
      sums(static_cast<std::size_t>(hi - lo + 1) * kHours, 0.0) {}

void DenseTable::merge(const DenseTable& other) {
    for (std::size_t i = 0; i < counts.size(); ++i) {
        counts[i] += other.counts[i];
        sums[i] += other.sums[i];
    }
}

Results DenseTable::to_results() const {
    Results r;
    for (int z = 0; z < zones; ++z)
        for (int h = 0; h < kHours; ++h) {
            const auto i = static_cast<std::size_t>(z) * kHours + static_cast<std::size_t>(h);
            if (counts[i]) r.emplace(Key{min_zone + z, h}, Aggregate{counts[i], sums[i]});
        }
    return r;
}

bool dense_range(std::span<const Trip> trips, int& lo, int& hi) {
    if (trips.empty()) return false;
    lo = hi = trips.front().pickup_zone;
    for (const auto& t : trips) {
        if (t.pickup_zone < lo) lo = t.pickup_zone;
        if (t.pickup_zone > hi) hi = t.pickup_zone;
    }
    const auto span = static_cast<long long>(hi) - lo + 1;
    return static_cast<std::size_t>(span) * kHours <= kMaxDenseBins;
}

Results aggregate_map(std::span<const Trip> trips) {
    Results result;
    for (const auto& trip : trips) {
        if (!valid(trip)) throw std::invalid_argument("Cannot aggregate invalid trip");
        result[{trip.pickup_zone, trip.hour}].add(trip.distance);
    }
    return result;
}

Results aggregate_serial(std::span<const Trip> trips) {
    int lo = 0, hi = 0;
    if (!dense_range(trips, lo, hi)) return aggregate_map(trips);
    DenseTable table(lo, hi);
    for (const auto& t : trips) table.add(t);
    return table.to_results();
}

void merge(Results& destination, const Results& source) {
    for (const auto& [key, value] : source) {
        auto& target = destination[key];
        target.trip_count += value.trip_count;
        target.total_distance += value.total_distance;
    }
}

void write_results(std::ostream& out, const Results& results) {
    out << "pickup_zone_id,hour_of_day,trip_count,total_distance,average_distance\n" << std::fixed << std::setprecision(10);
    for (const auto& [key, value] : results)
        out << key.pickup_zone << ',' << key.hour << ',' << value.trip_count << ',' << value.total_distance << ',' << value.average_distance() << '\n';
    if (!out) throw std::runtime_error("Failed writing results");
}

void write_results(const std::filesystem::path& path, const Results& results) {
    if (!path.parent_path().empty()) std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path);
    if (!output) throw std::runtime_error("Cannot open output CSV: " + path.string());
    write_results(output, results);
}

}  // namespace taxi
