#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iosfwd>
#include <map>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace taxi {

inline constexpr const char* kInputHeader = "pickup_zone_id,hour_of_day,trip_distance";
inline constexpr int kHours = 24;

struct Trip { int pickup_zone; int hour; double distance; };

struct Key {
    int pickup_zone; int hour;
    friend bool operator<(const Key& a, const Key& b) noexcept {
        return a.pickup_zone < b.pickup_zone || (a.pickup_zone == b.pickup_zone && a.hour < b.hour);
    }
};

struct Aggregate {
    std::uint64_t trip_count = 0;
    double total_distance = 0.0;
    void add(double distance) noexcept { ++trip_count; total_distance += distance; }
    double average_distance() const noexcept { return trip_count ? total_distance / static_cast<double>(trip_count) : 0.0; }
};
using Results = std::map<Key, Aggregate>;

// Dense (zone, hour) table used when the zone IDs fall in a small range.
// TLC zones are 1..265, so the table has a few thousand bins and fits in L2.
// Counts and sums are kept in separate arrays (structure of arrays).
struct DenseTable {
    int min_zone = 0;
    int zones = 0;
    std::vector<std::uint64_t> counts;
    std::vector<double> sums;

    DenseTable() = default;
    DenseTable(int lo, int hi);
    std::size_t bins() const noexcept { return counts.size(); }
    std::size_t index(int zone, int hour) const noexcept {
        return static_cast<std::size_t>(zone - min_zone) * kHours + static_cast<std::size_t>(hour);
    }
    void add(const Trip& t) noexcept { const auto i = index(t.pickup_zone, t.hour); ++counts[i]; sums[i] += t.distance; }
    void merge(const DenseTable& other);
    Results to_results() const;
};

// Largest table we are willing to allocate per thread before falling back to std::map.
inline constexpr std::size_t kMaxDenseBins = std::size_t{1} << 20;

bool valid(const Trip& trip) noexcept;

// Parses one data line (without the newline). Throws std::invalid_argument on bad input.
Trip parse_line(std::string_view line);

// Reads the whole file into memory and checks the header.
// On return `body_offset` points at the first byte after the header line.
std::string read_file(const std::filesystem::path& path, std::size_t& body_offset);

// Parses every line of `text`. `first_line` is only used for error messages.
void parse_range(std::string_view text, std::vector<Trip>& out, std::size_t first_line);

// Same, but writes into `out`, which must have room for line_count(text) trips.
// Returns the number of trips written (empty lines are skipped).
std::size_t parse_into(std::string_view text, Trip* out, std::size_t first_line);
std::size_t line_count(std::string_view text) noexcept;

std::vector<Trip> load_csv(const std::filesystem::path& path);

bool dense_range(std::span<const Trip> trips, int& lo, int& hi);
Results aggregate_map(std::span<const Trip> trips);
Results aggregate_serial(std::span<const Trip> trips);
void merge(Results& destination, const Results& source);
void write_results(const std::filesystem::path& path, const Results& results);
void write_results(std::ostream& out, const Results& results);

}  // namespace taxi
