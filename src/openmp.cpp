#include "analytics.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#ifdef TAXI_HAS_OPENMP
#include <omp.h>
#endif

int main(int argc,char** argv) try {
    std::filesystem::path input="data/processed/taxi_2025_clean.csv", output="results/openmp.csv";
    int threads=1; std::string schedule="static";
    for(int i=1;i<argc;++i){ const std::string arg=argv[i]; if(i+1>=argc) throw std::runtime_error("Missing value for "+arg); const std::string val=argv[++i];
        if(arg=="--input") input=val; else if(arg=="--output") output=val; else if(arg=="--threads") threads=std::stoi(val); else if(arg=="--schedule") schedule=val; else throw std::runtime_error("Unknown option: "+arg); }
    if(threads!=1&&threads!=2&&threads!=4&&threads!=8) throw std::runtime_error("--threads must be 1, 2, 4, or 8");
    if(schedule!="static"&&schedule!="dynamic"&&schedule!="guided") throw std::runtime_error("--schedule must be static, dynamic, or guided");
#ifndef TAXI_HAS_OPENMP
    if(threads>1) throw std::runtime_error("This build has no OpenMP support; install an OpenMP-capable compiler/runtime and reconfigure CMake");
#endif
    using clock=std::chrono::steady_clock; const auto start=clock::now(); const auto trips=taxi::load_csv(input); const auto loaded=clock::now();
    taxi::Results results;
#ifdef TAXI_HAS_OPENMP
    omp_set_num_threads(threads);
    omp_sched_t kind = schedule=="dynamic" ? omp_sched_dynamic : schedule=="guided" ? omp_sched_guided : omp_sched_static;
    omp_set_schedule(kind,1);
    const int capacity=threads;
    std::vector<taxi::Results> local(static_cast<std::size_t>(capacity));
#pragma omp parallel for schedule(runtime)
    for(std::int64_t i=0;i<static_cast<std::int64_t>(trips.size());++i){
        auto& own=local[static_cast<std::size_t>(omp_get_thread_num())];
        const auto& t=trips[static_cast<std::size_t>(i)];
        own[{t.pickup_zone,t.hour}].add(t.distance);
    }
    for(const auto& part:local) taxi::merge(results,part);
#else
    (void)schedule;
    results=taxi::aggregate_serial(trips);
#endif
    const auto aggregated=clock::now(); taxi::write_results(output,results); const auto written=clock::now();
    const auto ms=[](auto a,auto b){return std::chrono::duration<double,std::milli>(b-a).count();};
    std::cout << "records="<<trips.size()<<"\ngroups="<<results.size()<<"\nthreads="<<threads<<"\nschedule="<<schedule<<"\nloading_ms="<<ms(start,loaded)<<"\naggregation_ms="<<ms(loaded,aggregated)<<"\nwriting_ms="<<ms(aggregated,written)<<"\nend_to_end_ms="<<ms(start,written)<<'\n'; return 0;
}catch(const std::exception& e){std::cerr<<"openmp: "<<e.what()<<'\n';return 2;}
