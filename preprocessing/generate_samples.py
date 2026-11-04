#!/usr/bin/env python3
"""Create deterministic, evenly spaced approximate-size CSV samples."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path

MIB = 1024 * 1024

def make_sample(source: Path, destination: Path, target_bytes: int) -> tuple[int, int]:
    if not source.is_file():
        raise FileNotFoundError(f"Cleaned CSV not found: {source}")
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != ["pickup_zone_id", "hour_of_day", "trip_distance"]:
            raise ValueError("Input CSV has an unexpected header")
        count = sum(1 for row in reader if row)
    if count == 0:
        raise ValueError("Input CSV contains no records")
    source_size = source.stat().st_size
    wanted = min(count, max(1, round(count * target_bytes / source_size)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected = 0
    with source.open(newline="", encoding="utf-8") as src, destination.open("w", newline="", encoding="utf-8") as dst:
        reader, writer = csv.reader(src), csv.writer(dst, lineterminator="\n")
        writer.writerow(next(reader))
        index = 0
        for row in reader:
            if row and ((index * wanted) // count != ((index + 1) * wanted) // count):
                writer.writerow(row)
                selected += 1
            index += 1
    return selected, destination.stat().st_size

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/taxi_2025_clean.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/samples"))
    args = parser.parse_args()
    for label, size in (("100mb", 100 * MIB), ("500mb", 500 * MIB)):
        path = args.output_dir / f"taxi_{label}.csv"
        records, actual = make_sample(args.input, path, size)
        print(f"{path}: {records:,} records, {actual:,} bytes ({actual / MIB:.2f} MiB)")

if __name__ == "__main__":
    main()
