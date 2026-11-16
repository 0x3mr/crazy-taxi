# Crazy Taxi

SW 401 course project. Crazy Taxi processes the NYC Yellow Taxi Trip Records for
January–December 2025 (48.7 M trips). For every pickup zone and pickup hour it
reports the trip count, total distance and average distance. Phase 1 contains
the preprocessing, a C++ serial baseline, an OpenMP version and the
memory-hierarchy experiments.

- Dataset and team: [`docs/phase0_proposal.md`](docs/phase0_proposal.md)
- Phase 1 report: [`report.pdf`](report.pdf) (source in `docs/report/`)
- Download instructions: [`data/README.md`](data/README.md)

## Repository layout

| path | contents |
|---|---|
| `preprocessing/` | Parquet → CSV cleaning, sample generation |
| `include/`, `src/` | shared analytics code, `serial`, `openmp`, `cache_test`, `false_sharing` |
| `scripts/` | build wrappers, benchmark runner, summary tables, plots, profiling |
| `tests/` | synthetic tests, result comparison, PyArrow cross-check |
| `data/` | download instructions and a 10k-row sample (full data is not committed) |
| `results/` | raw timings, summary tables, experiment logs, preprocessing statistics |
| `plots/` | figures used in the report |
| `docs/` | Phase 0 proposal and report source |

## Requirements

- CMake ≥ 3.20 and a C++20 compiler with OpenMP (GCC 11+ recommended; we used
  MinGW-w64 GCC 13.2 from MSYS2 on Windows and GCC on Linux).
- Python ≥ 3.10 with the packages in `requirements.txt` (PyArrow, matplotlib, markdown).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Build and test

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
```

On Windows with MSYS2, add `-G Ninja -DCMAKE_CXX_COMPILER=g++` (or use
`scripts/build.ps1`). MinGW builds are linked statically, so the `.exe` files run
without the MSYS2 DLLs on `PATH`.

The tests use only synthetic data: hand-checked groups, 20k random trips run
through every strategy/schedule/thread count, malformed input with the expected
line number in the error, and the preprocessing rules on a small Parquet file.

## 1. Preprocessing

Download the twelve monthly files into `data/raw/` (see `data/README.md`), then:

```bash
python preprocessing/prepare_taxi.py          # -> data/processed/taxi_2025_clean.csv (+ .stats.json)
python preprocessing/generate_samples.py      # -> data/samples/taxi_100mb.csv, taxi_250mb.csv
```

Rules, applied in order (each dropped row is counted under its first failing rule):

| rule | dropped in 2025 |
|---|---|
| pickup timestamp missing | 0 |
| pickup not in 2025 | 29 |
| zone missing or outside 1..265 | 0 |
| distance missing / NaN / ≤ 0 | 1,402,958 |
| distance > 100 miles | 2,870 |
| exact duplicate row (10 trip fields) within a month | 0 |

| | records | size |
|---|---|---|
| before (12 Parquet files) | 48,722,602 | 829,973,299 B compressed, 1.29 GB uncompressed |
| after (CSV) | 47,316,745 | 536,349,586 B |
| 100 MB sample | 9,250,534 | 104,857,584 B |
| 250 MB sample | 23,126,336 | 262,144,884 B |

The cleaned CSV is only 536 MB because it keeps three columns, so the second
sample is 250 MB instead of 500 MB. The pickup hour is the stored local NYC
wall-clock hour. Full statistics: `results/preprocessing_stats.json`.

## 2. Running

```bash
./build/serial --input data/processed/taxi_2025_clean.csv --output results/serial.csv
./build/openmp --input data/processed/taxi_2025_clean.csv --output results/openmp.csv \
    --threads 8 --schedule static
```

`openmp` options:

| option | values | default |
|---|---|---|
| `--threads` | any positive number | 1 |
| `--schedule` | `static`, `dynamic`, `guided` (applied with `schedule(runtime)`) | `static` |
| `--chunk` | chunk size for the schedule, 0 = OpenMP default | 0 |
| `--strategy` | `local` (per-thread tables), `reduction` (array-section reduction), `atomic`, `critical`, `map` (per-thread `std::map`) | `local` |
| `--parse-tasks` | number of parse tasks, 0 = 8 per thread | 0 |

Both programs print `read_ms`, `parse_ms`, `aggregation_ms`, `writing_ms` and
`end_to_end_ms`.

Checking results:

```bash
python tests/validate_results.py results/serial.csv results/openmp.csv
python tests/crosscheck_pyarrow.py data/processed/taxi_2025_clean.csv results/serial.csv
```

Counts must match exactly; sums may differ in the last digits because the
parallel version adds in a different order.

## 3. Benchmarks, tables and plots

```bash
python scripts/benchmark.py --runs 5 --serial build/serial --openmp build/openmp
python scripts/summarize.py      # results/summary*.csv and results/summary.md
python scripts/plot_results.py   # plots/*.png
```

`benchmark.py` runs three experiments: thread scaling for every schedule on all
three dataset sizes, the five aggregation strategies on the 100 MB sample, and
chunk sizes 1/64/4096/65536 for each schedule on the full data. Every
configuration is repeated and the summary uses the median.

## 4. Memory hierarchy and profiling

```bash
./build/cache_test --input data/processed/taxi_2025_clean.csv > results/cache_test.txt
./build/false_sharing --input data/processed/taxi_2025_clean.csv > results/false_sharing.txt
```

`cache_test` sums the 47.3 M distances with strides 1…256 (every element is
still read once per pass) and compares the 16-byte `Trip` array (AoS) with a
packed `double` array (SoA). `false_sharing` updates per-thread counters that are
adjacent, padded to 64 bytes, or private with `reduction(+)`.

gprof (GCC/Clang):

```bash
cmake -S . -B build-gprof -DCMAKE_BUILD_TYPE=Release -DTAXI_GPROF=ON
cmake --build build-gprof
./build-gprof/serial --input data/samples/taxi_100mb.csv --output build-gprof/out.csv
gprof build-gprof/serial gmon.out > results/profiling/gprof_serial.txt
```

On Linux, hardware counters can be collected with
`perf stat -e cycles,instructions,cache-references,cache-misses ./build/cache_test --input ... --stride 1`
(repeat for other strides).
