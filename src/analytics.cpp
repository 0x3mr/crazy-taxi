#include "analytics.hpp"
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace taxi {
bool valid(const Trip& t) noexcept { return t.hour >= 0 && t.hour <= 23 && std::isfinite(t.distance) && t.distance > 0.0; }

std::vector<Trip> load_csv(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot open input CSV: " + path.string());
    std::string line;
    if (!std::getline(input, line))
        throw std::runtime_error("Input CSV is empty");
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != "pickup_zone_id,hour_of_day,trip_distance")
        throw std::runtime_error("Unexpected CSV header; expected pickup_zone_id,hour_of_day,trip_distance");
    std::vector<Trip> trips;
    std::size_t line_number = 1;
    while (std::getline(input, line)) {
        ++line_number;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        std::istringstream row(line);
        std::string zone_text, hour_text, distance_text, extra;
        if (!std::getline(row, zone_text, ',') || !std::getline(row, hour_text, ',') || !std::getline(row, distance_text) || std::getline(row, extra, ','))
            throw std::runtime_error("Malformed CSV row at line " + std::to_string(line_number));
        try {
            std::size_t n1=0,n2=0,n3=0;
            const int zone=std::stoi(zone_text,&n1), hour=std::stoi(hour_text,&n2);
            const double distance=std::stod(distance_text,&n3);
            if (n1 != zone_text.size() || n2 != hour_text.size() || n3 != distance_text.size()) throw std::invalid_argument("trailing characters");
            Trip trip{zone,hour,distance};
            if (!valid(trip)) throw std::invalid_argument("invalid value");
            trips.push_back(trip);
        } catch (const std::exception& e) {
            throw std::runtime_error("Invalid CSV record at line " + std::to_string(line_number) + ": " + e.what());
        }
    }
    if (input.bad()) throw std::runtime_error("Error reading input CSV: " + path.string());
    return trips;
}

Results aggregate_serial(const std::vector<Trip>& trips) {
    Results result;
    for (const auto& trip : trips) {
        if (!valid(trip)) throw std::invalid_argument("Cannot aggregate invalid trip");
        result[{trip.pickup_zone, trip.hour}].add(trip.distance);
    }
    return result;
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
}
