#!/usr/bin/env python3
"""Create deterministic, evenly spaced approximate-size CSV samples.

Rows are picked at a fixed spacing over the whole cleaned file, so each
sample covers all twelve months instead of only January.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MIB = 1024 * 1024
HEADER = b"pickup_zone_id,hour_of_day,trip_distance"


def count_rows(source: Path) -> int:
    lines = 0
    with source.open("rb") as f:
        while chunk := f.read(16 * MIB):
            lines += chunk.count(b"\n")
    return lines - 1  # header


def make_sample(source: Path, destination: Path, target_bytes: int) -> tuple[int, int]:
    if not source.is_file():
        raise FileNotFoundError(f"Cleaned CSV not found: {source}")
    with source.open("rb") as f:
        if f.readline().rstrip(b"\r\n") != HEADER:
            raise ValueError("Input CSV has an unexpected header")
    count = count_rows(source)
    if count <= 0:
        raise ValueError("Input CSV contains no records")
    wanted = min(count, max(1, round(count * target_bytes / source.stat().st_size)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected = 0
    with source.open("rb") as src, destination.open("wb") as dst:
        dst.write(src.readline())
        for index, row in enumerate(src):
            if not row.strip():
                continue
            if (index * wanted) // count != ((index + 1) * wanted) // count:
                dst.write(row if row.endswith(b"\n") else row + b"\n")
                selected += 1
    return selected, destination.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/taxi_2025_clean.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/samples"))
    parser.add_argument("--sizes", default="100,250", help="comma-separated sample sizes in MiB (default 100,250)")
    parser.add_argument("--tiny", type=Path, default=Path("data/sample/taxi_sample_10k.csv"),
                        help="also write a ~10k-row sample that is small enough to commit")
    args = parser.parse_args()
    full = args.input.stat().st_size
    for size in (int(s) for s in args.sizes.split(",")):
        if size * MIB >= full:
            print(f"skipping {size} MiB: cleaned file is only {full / MIB:.0f} MiB")
            continue
        path = args.output_dir / f"taxi_{size}mb.csv"
        records, actual = make_sample(args.input, path, size * MIB)
        print(f"{path}: {records:,} records, {actual:,} bytes ({actual / MIB:.2f} MiB)")
    if args.tiny:
        records, actual = make_sample(args.input, args.tiny, 10_000 * full // max(1, count_rows(args.input)))
        print(f"{args.tiny}: {records:,} records, {actual:,} bytes")


if __name__ == "__main__":
    main()
