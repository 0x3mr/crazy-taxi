#pragma once

#include <cstdint>
#include <filesystem>
#include <iosfwd>
#include <map>
#include <string>
#include <vector>

namespace taxi {
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

bool valid(const Trip& trip) noexcept;
std::vector<Trip> load_csv(const std::filesystem::path& path);
Results aggregate_serial(const std::vector<Trip>& trips);
void merge(Results& destination, const Results& source);
void write_results(const std::filesystem::path& path, const Results& results);
void write_results(std::ostream& out, const Results& results);
}
