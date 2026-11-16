# Data

The full dataset is not stored in Git. Only `sample/taxi_sample_10k.csv`
(10,000 cleaned rows, evenly spaced over the year) is committed, so the code can
be tried without downloading anything:

```bash
./build/serial --input data/sample/taxi_sample_10k.csv --output results/sample_serial.csv
```

## Download

Get the twelve 2025 yellow-taxi files from the TLC page
(<https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>) and put them in
`data/raw/`. The direct links follow this pattern:

```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-MM.parquet
```

For example with curl (Linux, macOS, Git Bash):

```bash
mkdir -p data/raw
for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  curl -fL -o data/raw/yellow_tripdata_2025-$m.parquet \
    https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-$m.parquet
done
```

Sizes we downloaded (November 2026), 829,973,299 bytes in total:

| month | bytes | records |
|---|---|---|
| 01 | 59,158,238 | 3,475,226 |
| 02 | 60,343,086 | 3,577,543 |
| 03 | 69,964,745 | 4,145,257 |
| 04 | 67,352,824 | 3,970,553 |
| 05 | 77,837,865 | 4,591,845 |
| 06 | 73,542,954 | 4,322,960 |
| 07 | 66,943,728 | 3,898,963 |
| 08 | 62,293,743 | 3,574,091 |
| 09 | 72,432,945 | 4,251,015 |
| 10 | 75,267,589 | 4,428,699 |
| 11 | 71,134,255 | 4,181,444 |
| 12 | 73,701,327 | 4,305,006 |

TLC sometimes republishes files with small corrections, so later downloads may
differ slightly.

## Layout after preprocessing

```
data/
  raw/          12 Parquet files (input, ignored by Git)
  processed/    taxi_2025_clean.csv + taxi_2025_clean.stats.json (ignored)
  samples/      taxi_100mb.csv, taxi_250mb.csv (ignored)
  sample/       taxi_sample_10k.csv (committed)
```

See the main README for the preprocessing commands. The statistics file from our
run is copied to `results/preprocessing_stats.json`.
