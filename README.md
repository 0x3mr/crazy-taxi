# Crazy Taxi

Crazy Taxi processes the NYC Yellow Taxi Trip Records for January through December 2025. It groups trips by pickup zone and pickup hour, then reports each group's trip count, total distance, and average distance. The sequential C++ program is the reference; the OpenMP program performs the same aggregation with thread-local maps.

Dataset source: [NYC Taxi and Limousine Commission trip record data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).

## Repository layout

- `preprocessing/`: Parquet cleaning and deterministic CSV sample generation.
- `include/`, `src/`: shared C++ analytics, serial/OpenMP programs, and cache experiment.
- `scripts/`: CMake wrappers, repeated benchmark runner, and plotting script.
- `tests/`: synthetic preprocessing, aggregation, and output validation checks.
- `data/`: local inputs and generated datasets. The whole directory is ignored by Git.
- `results/`, `plots/`: benchmark CSV and plots, available to commit when real measurements exist.

## Requirements

- CMake 3.20 or newer and a C++20 compiler (GCC, Clang, or compatible MSVC).
- OpenMP compiler/runtime for multi-thread runs. CMake warns and builds a serial fallback if OpenMP is unavailable; that build accepts one OpenMP thread only.
- Python 3.10 or newer. PyArrow is needed for Parquet preprocessing; matplotlib is needed for plotting.

Create and activate a Python virtual environment, then install the dependencies:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r preprocessing/requirements.txt matplotlib
```

On macOS, an OpenMP runtime such as `libomp` may need to be installed through the system's package manager and exposed to CMake. Windows needs a compiler with OpenMP support (MSVC supports its OpenMP subset); WSL2 is another option. Linux profiling with `perf` is optional and Linux-specific. No system packages are installed by this project.

## Build

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure
```

Convenience wrappers use the same CMake project:

```bash
./scripts/build.sh
# Windows PowerShell
.\scripts\build.ps1
```

CTest's Parquet test reports a skip when PyArrow is unavailable. Install the requirement and run it directly with `python tests/test_preprocessing.py` to execute it.

## Prepare the dataset

Download the twelve official monthly TLC files yourself and put them in `data/raw/` with these names:

```text
yellow_tripdata_2025-01.parquet
...
yellow_tripdata_2025-12.parquet
```

The cleaner requires all twelve files and reports missing files explicitly. It reads only pickup timestamp, pickup zone, and trip distance in batches. It preserves the timestamp's stored wall-clock hour without timezone shifting, drops rows with unusable timestamps, missing/non-integral zone IDs, or missing/non-finite/non-positive distances, and retains duplicate-looking rows. Statistics are printed and saved beside the output as `taxi_2025_clean.stats.json`.

```bash
python preprocessing/prepare_taxi.py \
  --input-dir data/raw \
  --output data/processed/taxi_2025_clean.csv \
  --batch-size 100000
python preprocessing/generate_samples.py \
  --input data/processed/taxi_2025_clean.csv \
  --output-dir data/samples
```

The sample generator uses a deterministic evenly spaced selection over the complete cleaned CSV. Targets are 100 MiB and 500 MiB; actual file sizes and row counts are printed because exact target sizes depend on row lengths. Samples are generated from the cleaned data, not raw Parquet.

## Run the analytics

```bash
./build/serial --input data/processed/taxi_2025_clean.csv --output results/serial.csv
./build/openmp --input data/processed/taxi_2025_clean.csv \
  --threads 4 --schedule static --output results/openmp.csv
```

OpenMP accepts 1, 2, 4, or 8 threads and `static`, `dynamic`, or `guided` scheduling (static is the default). Results are sorted by zone and hour. Trip counts should match exactly; floating-point totals can differ slightly because parallel reduction changes addition order. `tests/validate_results.py` checks counts exactly and uses relative tolerance `1e-10` and absolute tolerance `1e-9` for sums and averages. Program timing output separates loading/parsing, aggregation, writing, and end-to-end time; aggregation is the comparison metric.

## Tests

Synthetic tests do not require the NYC dataset:

```bash
ctest --test-dir build --output-on-failure
python tests/test_preprocessing.py
```

The preprocessing test creates synthetic Parquet files in a temporary directory when PyArrow is installed. Analytics tests verify manually calculated expected results, unusual zone IDs, malformed input rejection, OpenMP output, and the synthetic cache experiment. Temporary inputs are removed afterward.

## Benchmarks and plots

After preparing the cleaned data and both samples, run:

```bash
python scripts/benchmark.py --runs 3
python scripts/plot_results.py
```

The benchmark measures sequential and OpenMP runs on 100 MiB, 500 MiB, and full cleaned data, by default with 1/2/4/8 threads and all three schedules. It writes raw run measurements and derived speedup, efficiency, and serial-fraction estimates to `results/timings.csv`. Speedup and efficiency are based on the median serial aggregation time for that dataset; parallel values are per run. The `--smoke` option exercises the benchmark runner using a tiny temporary CSV and should not be used as performance data. Plots use the median for each dataset/schedule/thread combination.

Do not treat synthetic smoke timings as experimental findings. Run actual experiments only after the real dataset is prepared and the machine is otherwise suitable for benchmarking.

## Cache experiment

The cache test loads trip distances from processed CSV or creates a deterministic synthetic vector. Each stride visits every element once per pass; five passes are timed, and a checksum is reported. Use `--stride` to select one layout when collecting hardware counters.

```bash
./build/cache_test --input data/processed/taxi_2025_clean.csv
./build/cache_test --synthetic 1000000
```

On Linux, hardware counters can optionally be collected with:

```bash
perf stat -e cycles,instructions,cache-references,cache-misses \
  ./build/cache_test --input data/processed/taxi_2025_clean.csv --stride 1
# Repeat with --stride 8, --stride 64, and --stride 256 for comparison.
```

`perf stat` is Linux-specific and may be restricted by kernel permissions or virtualized hardware. The cache program itself is portable C++20; macOS and Windows require their own profiling tools if hardware-counter measurements are needed. Benchmark runs create `results/timings.csv` and plots under `plots/`; run `tests/validate_results.py` on the serial and OpenMP outputs before treating them as equivalent. The course report is intentionally a separate deliverable after the cache profiling and analysis are complete.
