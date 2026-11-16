#include "analytics.hpp"

#include <chrono>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    std::filesystem::path input = "data/processed/taxi_2025_clean.csv", output = "results/serial.csv";
    std::string strategy = "dense";
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (i + 1 >= argc) throw std::runtime_error("Missing value for " + arg);
        const std::string val = argv[++i];
        if (arg == "--input") input = val;
        else if (arg == "--output") output = val;
        else if (arg == "--strategy") strategy = val;
        else throw std::runtime_error("Unknown option: " + arg);
    }
    if (strategy != "dense" && strategy != "map") throw std::runtime_error("--strategy must be dense or map");

    using clock = std::chrono::steady_clock;
    const auto start = clock::now();
    std::size_t offset = 0;
    const std::string text = taxi::read_file(input, offset);
    const auto read_done = clock::now();
    std::vector<taxi::Trip> trips;
    trips.reserve((text.size() - offset) / 20 + 1);
    taxi::parse_range(std::string_view(text).substr(offset), trips, 2);
    const auto loaded = clock::now();
    const auto results = strategy == "map" ? taxi::aggregate_map(trips) : taxi::aggregate_serial(trips);
    const auto aggregated = clock::now();
    taxi::write_results(output, results);
    const auto written = clock::now();

    const auto ms = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
    std::cout << "records=" << trips.size() << "\ngroups=" << results.size() << "\nstrategy=" << strategy
              << "\nread_ms=" << ms(start, read_done) << "\nparse_ms=" << ms(read_done, loaded)
              << "\nloading_ms=" << ms(start, loaded) << "\naggregation_ms=" << ms(loaded, aggregated)
              << "\nwriting_ms=" << ms(aggregated, written) << "\nend_to_end_ms=" << ms(start, written) << '\n';
    return 0;
} catch (const std::exception& e) {
    std::cerr << "serial: " << e.what() << '\n';
    return 2;
}
