cmake_minimum_required(VERSION 3.20)
project(crazy_taxi VERSION 1.1 LANGUAGES CXX)
include(CTest)
find_package(OpenMP)
find_package(Python3 COMPONENTS Interpreter)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# -DTAXI_GPROF=ON builds with -pg for gprof (GCC/Clang only).
option(TAXI_GPROF "Build with gprof instrumentation" OFF)
if(TAXI_GPROF AND NOT MSVC)
  add_compile_options(-pg -fno-omit-frame-pointer)
  add_link_options(-pg)
  if(MINGW)
    # gprof on Windows only records samples for a fixed load address.
    add_link_options(-no-pie -Wl,--disable-dynamicbase)
  endif()
endif()

# MinGW: link the runtime statically so the .exe files run outside the MSYS2 shell
# (not for gprof builds, which then record no samples).
if(MINGW AND NOT TAXI_GPROF)
  add_link_options(-static)
endif()

add_library(taxi_analytics src/analytics.cpp)
target_include_directories(taxi_analytics PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(taxi_analytics PUBLIC cxx_std_20)
if(MSVC)
  target_compile_options(taxi_analytics PUBLIC /W4 /permissive-)
else()
  target_compile_options(taxi_analytics PUBLIC -Wall -Wextra -Wpedantic)
endif()

add_executable(serial src/serial.cpp)
target_link_libraries(serial PRIVATE taxi_analytics)
add_executable(openmp src/openmp.cpp)
target_link_libraries(openmp PRIVATE taxi_analytics)
add_executable(cache_test src/cache_test.cpp)
target_link_libraries(cache_test PRIVATE taxi_analytics)

if(OpenMP_CXX_FOUND)
  target_link_libraries(openmp PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(openmp PRIVATE TAXI_HAS_OPENMP=1)
  add_executable(false_sharing src/false_sharing.cpp)
  target_link_libraries(false_sharing PRIVATE taxi_analytics OpenMP::OpenMP_CXX)
else()
  message(WARNING "OpenMP was not found: openmp supports only --threads 1 and false_sharing is not built")
endif()

if(BUILD_TESTING AND Python3_Interpreter_FOUND)
  add_test(NAME analytics_synthetic COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_analytics.py
    --serial $<TARGET_FILE:serial> --openmp $<TARGET_FILE:openmp> --cache $<TARGET_FILE:cache_test>
    --openmp-enabled $<BOOL:${OpenMP_CXX_FOUND}>)
  add_test(NAME results_validation COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/validate_results.py --self-test)
  add_test(NAME preprocessing_synthetic COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_preprocessing.py)
  add_test(NAME benchmark_smoke COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/scripts/benchmark.py
    --smoke --serial $<TARGET_FILE:serial> --openmp $<TARGET_FILE:openmp> --output ${CMAKE_CURRENT_BINARY_DIR}/smoke_timings.csv)
endif()
