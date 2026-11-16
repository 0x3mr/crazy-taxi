# Phase 0 – Dataset choice and team

SW 401 Parallel and Distributed Systems, Fall 2025 – team Crazy Taxi

## Team and roles

| Member | Role | Main Phase 1 work |
|---|---|---|
| Amr Abdelfattah | Parallelization Lead | OpenMP aggregation (thread-local tables, reduction / atomic / critical variants), schedules |
| Momen Sanad | Performance Analyst | Benchmark runs, speedup / efficiency / serial-fraction tables, Amdahl and Gustafson analysis, plots |
| Khalid | Code Integrator / Tester | CMake build, synthetic tests, serial-vs-parallel validation, cache and false-sharing experiments |
| Abdelrahman Abdelrassoul | Documentation Coordinator | Preprocessing write-up, README, report, demo video |

Everyone reviews the others' pull requests, and each phase's work is split so that
every member owns one part of the code and one part of the report.

## Dataset

**NYC TLC Yellow Taxi Trip Records, January–December 2025.**

- Source: NYC Taxi & Limousine Commission,
  <https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>
- Files: `yellow_tripdata_2025-01.parquet` … `yellow_tripdata_2025-12.parquet`
  (download links are in [`data/README.md`](../data/README.md))
- Raw size: 12 Parquet files, 829,973,299 bytes compressed (≈ 0.83 GB),
  1.29 GB uncompressed, **48,722,602 trip records** with 20 columns each
- Licence: public NYC Open Data

Check against the course rules:

| Requirement | How the dataset meets it |
|---|---|
| ≥ 1 GB or ≈ 10 M records | Both: 48.7 M records (about 5× the record threshold) and 1,292,228,587 bytes uncompressed according to the Parquet metadata. The cleaned three-column CSV that the C++ code reads is 536 MB. |
| Processable in parallel | Every trip is an independent record, so the file can be cut at any line boundary and each piece processed alone. Results are sums and counts, which are associative, so partial results merge in any order. |
| Line-based text / CSV | Converted once from Parquet to a three-column CSV (one trip per line), which is also exactly what Hadoop Streaming needs in Phase 3. |
| Meaningful computation | Group-by aggregation (see below), not just reading. |

## Problem

For every **(pickup zone, pickup hour)** pair, compute the number of trips, the
total distance and the average distance. There are 265 TLC zones × 24 hours, so
up to 6,360 groups (6,159 actually appear in 2025). This is the spatial /
time-series direction from the project description: it shows where and when
taxis are busy and how long the trips are.

Fields used: `tpep_pickup_datetime` (for the hour), `PULocationID` (zone) and
`trip_distance` (miles). The other fields are used only to detect duplicate rows
during preprocessing.

## Plan for the three phases

1. **Phase 1:** clean the data, write a verified C++ serial baseline, parallelise
   parsing and aggregation with OpenMP, and measure speedup and cache behaviour.
2. **Phase 2:** each MPI rank reads its own byte range of the CSV, aggregates
   locally, and the 6,360-bin tables are combined with `MPI_Reduce`; ping-pong
   and overlap experiments as in Lab 7.
3. **Phase 3:** a Hadoop Streaming job with a C++ mapper that emits
   `zone,hour → distance` and a reducer (also usable as a combiner) that sums.
   Its output is compared with the serial, OpenMP and MPI results.

Programming models across the project: OpenMP, MPI, Hadoop Streaming, and
C++ threads/atomics (thread-pool variant planned in Phase 2).
