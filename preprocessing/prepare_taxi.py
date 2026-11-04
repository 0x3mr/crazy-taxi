#!/usr/bin/env python3
"""Convert the twelve monthly TLC Parquet files into validated trip rows."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

MONTHS = [f"yellow_tripdata_2025-{month:02d}.parquet" for month in range(1, 13)]
COLUMNS = ["tpep_pickup_datetime", "PULocationID", "trip_distance"]


def valid_row(timestamp: Any, zone: Any, distance: Any) -> tuple[int, int, float] | str:
    """Return output values or the exclusive reason this input row is discarded."""
    if timestamp is None:
        return "invalid_timestamp"
    try:
        # Arrow timestamps preserve their stored wall-clock hour; no timezone conversion.
        hour = int(timestamp.hour)
        if not 0 <= hour <= 23:
            return "invalid_timestamp"
    except (AttributeError, TypeError, ValueError, OverflowError):
        return "invalid_timestamp"
    try:
        if zone is None:
            return "invalid_zone"
        zone_id = int(zone)
        if isinstance(zone, float) and (not math.isfinite(zone) or zone != zone_id):
            return "invalid_zone"
    except (TypeError, ValueError, OverflowError):
        return "invalid_zone"
    try:
        trip_distance = float(distance)
    except (TypeError, ValueError, OverflowError):
        return "invalid_distance"
    if not math.isfinite(trip_distance) or trip_distance <= 0:
        return "invalid_distance"
    return zone_id, hour, trip_distance


def prepare(input_dir: Path, output: Path, batch_size: int) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("PyArrow is required. Install with: python -m pip install -r preprocessing/requirements.txt") from exc
    missing = [str(input_dir / name) for name in MONTHS if not (input_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required monthly Parquet file(s):\n  " + "\n  ".join(missing))
    output.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {"original_record_count": 0, "valid_record_count": 0,
        "discarded_record_count": 0, "discarded_by_reason": {"invalid_timestamp": 0,
        "invalid_zone": 0, "invalid_distance": 0}, "original_dataset_size_bytes": 0,
        "final_dataset_size_bytes": 0, "final_record_count": 0,
        "cleaning": "Keep pickup timestamp's stored local hour; discard null/unusable timestamps, null/non-integral zone IDs, and null/non-finite/non-positive distances. Identical selected-field rows are retained."}
    try:
        with output.open("w", newline="", encoding="utf-8") as dest:
            writer = csv.writer(dest, lineterminator="\n")
            writer.writerow(["pickup_zone_id", "hour_of_day", "trip_distance"])
            for filename in MONTHS:
                path = input_dir / filename
                stats["original_dataset_size_bytes"] += path.stat().st_size
                parquet = pq.ParquetFile(path)
                for batch in parquet.iter_batches(batch_size=batch_size, columns=COLUMNS):
                    columns = [batch.column(i).to_pylist() for i in range(3)]
                    for ts, zone, distance in zip(*columns):
                        stats["original_record_count"] += 1
                        result = valid_row(ts, zone, distance)
                        if isinstance(result, str):
                            stats["discarded_by_reason"][result] += 1
                            stats["discarded_record_count"] += 1
                        else:
                            writer.writerow([result[0], result[1], format(result[2], ".17g")])
                            stats["valid_record_count"] += 1
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Failed while processing Parquet input: {exc}") from exc
    stats["final_record_count"] = stats["valid_record_count"]
    stats["final_dataset_size_bytes"] = output.stat().st_size
    stats_path = output.with_suffix(".stats.json")
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))
    print(f"Statistics: {stats_path}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/taxi_2025_clean.csv"))
    parser.add_argument("--batch-size", type=int, default=100_000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    try:
        prepare(args.input_dir, args.output, args.batch_size)
    except (FileNotFoundError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
