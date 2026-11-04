#include "analytics.hpp"
#include <chrono>
#include <cmath>
#include <iostream>
#include <numeric>
#include <stdexcept>

int main(int argc,char** argv) try {
    std::size_t synthetic=1'000'000; std::filesystem::path input; std::size_t selected_stride=0;
    for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--synthetic"){if(++i>=argc)throw std::runtime_error("--synthetic needs an element count");synthetic=std::stoull(argv[i]);}else if(a=="--input"){if(++i>=argc)throw std::runtime_error("--input needs a file");input=argv[i];}else if(a=="--stride"){if(++i>=argc)throw std::runtime_error("--stride needs a value");selected_stride=std::stoull(argv[i]);}else throw std::runtime_error("Unknown option: "+a);}
    if(selected_stride!=0&&selected_stride!=1&&selected_stride!=8&&selected_stride!=64&&selected_stride!=256)throw std::runtime_error("--stride must be 1, 8, 64, or 256");
    std::vector<double> values;
    if(!input.empty()){const auto trips=taxi::load_csv(input);values.reserve(trips.size());for(const auto& t:trips)values.push_back(t.distance);}
    else {values.resize(synthetic);for(std::size_t i=0;i<values.size();++i)values[i]=0.5+static_cast<double>((i*17)%10000)/1000.0;}
    if(values.empty())throw std::runtime_error("No values to process");
    for(std::size_t stride:{1U,8U,64U,256U}){if(selected_stride&&selected_stride!=stride)continue;volatile double checksum=0.0;const auto start=std::chrono::steady_clock::now();
        for(std::size_t pass=0;pass<5;++pass)for(std::size_t offset=0;offset<stride&&offset<values.size();++offset)for(std::size_t i=offset;i<values.size();i+=stride)checksum=checksum+values[i];
        const auto end=std::chrono::steady_clock::now();std::cout<<"stride="<<stride<<" elements_per_pass="<<values.size()<<" passes=5 elapsed_ms="<<std::chrono::duration<double,std::milli>(end-start).count()<<" checksum="<<checksum<<'\n';}
    return 0;
}catch(const std::exception& e){std::cerr<<"cache_test: "<<e.what()<<'\n';return 2;}
