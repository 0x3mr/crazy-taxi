#!/usr/bin/env python3
"""Clean the twelve 2025 TLC yellow-taxi Parquet files into one CSV.

Output columns: pickup_zone_id,hour_of_day,trip_distance

Each input row is dropped for the first rule it breaks, in this order:
  invalid_timestamp  pickup timestamp missing
  out_of_period      pickup not in calendar year 2025 (the files contain a few
                     stray 2008/2009/2024/2026 timestamps)
  invalid_zone       pickup zone missing or outside the TLC zone IDs 1..265
  invalid_distance   distance missing, NaN/inf, or <= 0
  distance_outlier   distance above --max-distance miles (odometer errors)
  duplicate          exact copy of an earlier row in the same month, compared
                     on all trip fields listed in DEDUP_COLUMNS

The hour is the stored wall-clock hour (TLC timestamps are local NYC time),
no timezone conversion is applied.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

YEAR = 2025
MONTHS = [f"yellow_tripdata_{YEAR}-{month:02d}.parquet" for month in range(1, 13)]
REQUIRED = ["tpep_pickup_datetime", "PULocationID", "trip_distance"]
# Fields that identify a trip record. A row equal on all of these is a duplicate.
DEDUP_COLUMNS = ["VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime", "passenger_count",
                 "trip_distance", "PULocationID", "DOLocationID", "payment_type",
                 "fare_amount", "total_amount"]
REASONS = ["invalid_timestamp", "out_of_period", "invalid_zone", "invalid_distance",
           "distance_outlier", "duplicate"]
HEADER = "pickup_zone_id,hour_of_day,trip_distance\n"


def clean_table(table, max_distance: float, reasons: dict[str, int]):
    """Return the cleaned (zone, hour, distance) table and update the reason counters."""
    import pyarrow as pa
    import pyarrow.compute as pc

    ts = table["tpep_pickup_datetime"]
    zone = table["PULocationID"]
    dist = pc.cast(table["trip_distance"], pa.float64())

    rules = [
        ("invalid_timestamp", pc.is_valid(ts)),
        ("out_of_period", pc.equal(pc.year(ts), YEAR)),
        ("invalid_zone", pc.and_(pc.is_valid(zone), pc.and_(pc.greater_equal(zone, 1), pc.less_equal(zone, 265)))),
        ("invalid_distance", pc.and_(pc.is_finite(dist), pc.greater(dist, 0.0))),
        ("distance_outlier", pc.less_equal(dist, max_distance)),
    ]
    keep = None
    for name, ok in rules:
        ok = pc.fill_null(ok, False)
        dropped = pc.invert(ok) if keep is None else pc.and_(keep, pc.invert(ok))
        reasons[name] += pc.sum(pc.cast(dropped, pa.int64())).as_py() or 0
        keep = ok if keep is None else pc.and_(keep, ok)

    table = table.filter(keep)
    present = [c for c in DEDUP_COLUMNS if c in table.column_names]
    if table.num_rows:
        indexed = table.select(present).append_column("_row", pa.array(range(table.num_rows), pa.int64()))
        first = indexed.group_by(present, use_threads=True).aggregate([("_row", "min")])["_row_min"]
        before = table.num_rows
        table = table.take(pc.take(first, pc.sort_indices(first)))
        reasons["duplicate"] += before - table.num_rows

    return pa.table({
        "pickup_zone_id": pc.cast(table["PULocationID"], pa.int32()),
        "hour_of_day": pc.cast(pc.hour(table["tpep_pickup_datetime"]), pa.int32()),
        "trip_distance": pc.cast(table["trip_distance"], pa.float64()),
    })


def prepare(input_dir: Path, output: Path, max_distance: float = 100.0) -> dict[str, Any]:
    try:
        import pyarrow.compute as pc
        import pyarrow.csv as pcsv
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("PyArrow is required. Install with: python -m pip install -r preprocessing/requirements.txt") from exc
    missing = [str(input_dir / name) for name in MONTHS if not (input_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required monthly Parquet file(s):\n  " + "\n  ".join(missing))

    output.parent.mkdir(parents=True, exist_ok=True)
    reasons = {r: 0 for r in REASONS}
    stats: dict[str, Any] = {
        "original_dataset_size_bytes": 0, "original_record_count": 0,
        "final_dataset_size_bytes": 0, "final_record_count": 0, "discarded_record_count": 0,
        "discarded_by_reason": reasons, "max_distance_miles": max_distance, "months": [],
    }
    started = time.perf_counter()
    options = pcsv.WriteOptions(include_header=False, quoting_style="none")
    dist_min, dist_max, dist_sum = float("inf"), 0.0, 0.0
    with output.open("w", newline="", encoding="utf-8") as dest:
        dest.write(HEADER)
    with output.open("ab") as dest:
        for filename in MONTHS:
            path = input_dir / filename
            parquet = pq.ParquetFile(path)
            available = parquet.schema_arrow.names
            absent = [c for c in REQUIRED if c not in available]
            if absent:
                raise RuntimeError(f"{filename} is missing column(s): {', '.join(absent)}")
            columns = [c for c in DEDUP_COLUMNS if c in available]
            table = parquet.read(columns=columns)
            raw_rows = table.num_rows
            cleaned = clean_table(table, max_distance, reasons)
            if cleaned.num_rows:
                pcsv.write_csv(cleaned, dest, write_options=options)
                mm = pc.min_max(cleaned["trip_distance"]).as_py()
                dist_min, dist_max = min(dist_min, mm["min"]), max(dist_max, mm["max"])
                dist_sum += pc.sum(cleaned["trip_distance"]).as_py()
            stats["original_dataset_size_bytes"] += path.stat().st_size
            stats["original_record_count"] += raw_rows
            stats["final_record_count"] += cleaned.num_rows
            stats["months"].append({"file": filename, "raw_records": raw_rows, "clean_records": cleaned.num_rows})
            print(f"{filename}: {raw_rows:,} -> {cleaned.num_rows:,}", flush=True)

    stats["discarded_record_count"] = stats["original_record_count"] - stats["final_record_count"]
    stats["final_dataset_size_bytes"] = output.stat().st_size
    if stats["final_record_count"]:
        stats["clean_distance_min"] = dist_min
        stats["clean_distance_max"] = dist_max
        stats["clean_distance_mean"] = dist_sum / stats["final_record_count"]
    stats["seconds"] = round(time.perf_counter() - started, 1)
    stats_path = output.with_suffix(".stats.json")
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "months"}, indent=2))
    print(f"Statistics: {stats_path}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/taxi_2025_clean.csv"))
    parser.add_argument("--max-distance", type=float, default=100.0,
                        help="drop trips longer than this many miles (default 100)")
    args = parser.parse_args()
    if args.max_distance <= 0:
        parser.error("--max-distance must be positive")
    try:
        prepare(args.input_dir, args.output, args.max_distance)
    except (FileNotFoundError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
