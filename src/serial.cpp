#include "analytics.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    std::filesystem::path input="data/processed/taxi_2025_clean.csv", output="results/serial.csv";
    for (int i=1;i<argc;++i) {
        const std::string arg=argv[i];
        if (i+1>=argc) throw std::runtime_error("Missing value for " + arg);
        if (arg=="--input") input=argv[++i]; else if (arg=="--output") output=argv[++i]; else throw std::runtime_error("Unknown option: " + arg);
    }
    using clock=std::chrono::steady_clock;
    const auto start=clock::now();
    const auto trips=taxi::load_csv(input);
    const auto loaded=clock::now();
    const auto results=taxi::aggregate_serial(trips);
    const auto aggregated=clock::now();
    taxi::write_results(output,results);
    const auto written=clock::now();
    const auto ms=[](auto a,auto b){return std::chrono::duration<double,std::milli>(b-a).count();};
    std::cout << "records=" << trips.size() << "\ngroups=" << results.size() << "\nloading_ms=" << ms(start,loaded) << "\naggregation_ms=" << ms(loaded,aggregated) << "\nwriting_ms=" << ms(aggregated,written) << "\nend_to_end_ms=" << ms(start,written) << '\n';
    return 0;
} catch(const std::exception& e) { std::cerr << "serial: " << e.what() << '\n'; return 2; }
