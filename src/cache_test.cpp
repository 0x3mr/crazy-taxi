// Memory hierarchy experiments on the trip data.
//  1) stride: every element is visited once per pass, but in strided order,
//     so larger strides use fewer doubles out of each 64-byte cache line.
//  2) layout: summing distances from the Trip array (AoS, 16 bytes per trip)
//     against a packed distance array (SoA, 8 bytes per trip).
#include "analytics.hpp"

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
double elapsed_ms(std::chrono::steady_clock::time_point a) {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - a).count();
}
}  // namespace

int main(int argc, char** argv) try {
    std::size_t synthetic = 1'000'000;
    std::filesystem::path input;
    std::size_t only_stride = 0;
    int passes = 5;
    bool layout = true;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (++i >= argc) throw std::runtime_error(a + " needs a value");
            return argv[i];
        };
        if (a == "--synthetic") synthetic = std::stoull(next());
        else if (a == "--input") input = next();
        else if (a == "--stride") only_stride = std::stoull(next());
        else if (a == "--passes") passes = std::stoi(next());
        else if (a == "--no-layout") layout = false;
        else throw std::runtime_error("Unknown option: " + a);
    }
    if (only_stride != 0 && (only_stride > 1024 || (only_stride & (only_stride - 1)) != 0))
        throw std::runtime_error("--stride must be a power of two up to 1024");
    if (passes < 1) throw std::runtime_error("--passes must be positive");

    std::vector<taxi::Trip> trips;
    if (!input.empty()) {
        trips = taxi::load_csv(input);
    } else {
        trips.resize(synthetic);
        for (std::size_t i = 0; i < trips.size(); ++i)
            trips[i] = {static_cast<int>(1 + i % 265), static_cast<int>(i % 24), 0.5 + static_cast<double>((i * 17) % 10000) / 1000.0};
    }
    if (trips.empty()) throw std::runtime_error("No values to process");
    std::vector<double> values(trips.size());
    for (std::size_t i = 0; i < trips.size(); ++i) values[i] = trips[i].distance;

    for (std::size_t stride = 1; stride <= 256; stride *= 2) {
        if (only_stride && only_stride != stride) continue;
        volatile double checksum = 0.0;
        const auto t0 = std::chrono::steady_clock::now();
        for (int pass = 0; pass < passes; ++pass) {
            double s = 0.0;
            for (std::size_t offset = 0; offset < stride && offset < values.size(); ++offset)
                for (std::size_t i = offset; i < values.size(); i += stride) s += values[i];
            checksum = checksum + s;
        }
        const double ms = elapsed_ms(t0);
        std::cout << "test=stride stride=" << stride << " elements=" << values.size() << " passes=" << passes
                  << " elapsed_ms=" << ms << " ns_per_element=" << ms * 1e6 / (static_cast<double>(values.size()) * passes)
                  << " checksum=" << checksum << '\n';
    }

    if (layout && !only_stride) {
        volatile double aos = 0.0, soa = 0.0;
        // Four partial sums so the loop is limited by memory, not by the
        // latency of one long chain of dependent floating-point adds.
        const std::size_t n = values.size(), n4 = n - n % 4;
        auto t0 = std::chrono::steady_clock::now();
        for (int pass = 0; pass < passes; ++pass) {
            double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
            for (std::size_t i = 0; i < n4; i += 4) {
                s0 += trips[i].distance; s1 += trips[i + 1].distance;
                s2 += trips[i + 2].distance; s3 += trips[i + 3].distance;
            }
            for (std::size_t i = n4; i < n; ++i) s0 += trips[i].distance;
            aos = aos + (s0 + s1) + (s2 + s3);
        }
        const double aos_ms = elapsed_ms(t0);
        t0 = std::chrono::steady_clock::now();
        for (int pass = 0; pass < passes; ++pass) {
            double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
            for (std::size_t i = 0; i < n4; i += 4) {
                s0 += values[i]; s1 += values[i + 1];
                s2 += values[i + 2]; s3 += values[i + 3];
            }
            for (std::size_t i = n4; i < n; ++i) s0 += values[i];
            soa = soa + (s0 + s1) + (s2 + s3);
        }
        const double soa_ms = elapsed_ms(t0);
        std::cout << "test=layout layout=aos bytes_per_trip=" << sizeof(taxi::Trip) << " elapsed_ms=" << aos_ms << " checksum=" << aos << '\n';
        std::cout << "test=layout layout=soa bytes_per_trip=" << sizeof(double) << " elapsed_ms=" << soa_ms << " checksum=" << soa << '\n';
    }
    return 0;
} catch (const std::exception& e) {
    std::cerr << "cache_test: " << e.what() << '\n';
    return 2;
}
