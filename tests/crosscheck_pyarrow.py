#!/usr/bin/env python3
"""Check a C++ result file against an independent PyArrow group-by.

    python tests/crosscheck_pyarrow.py data/processed/taxi_2025_clean.csv results/serial.csv

Arrow's CSV reader and hash aggregation share no code with our C++ parser or
tables, so agreement here is a real correctness check, not a self-comparison.
Counts must match exactly; sums use a relative tolerance of 1e-9.
"""
import argparse
import csv
import math
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('trips')
    ap.add_argument('result')
    a = ap.parse_args()
    import pyarrow.csv as pcsv

    table = pcsv.read_csv(a.trips)
    grouped = table.group_by(['pickup_zone_id', 'hour_of_day']).aggregate(
        [('trip_distance', 'count'), ('trip_distance', 'sum')]).to_pydict()
    expected = {(z, h): (c, s) for z, h, c, s in zip(grouped['pickup_zone_id'], grouped['hour_of_day'],
                                                     grouped['trip_distance_count'], grouped['trip_distance_sum'])}
    with open(a.result, newline='', encoding='utf-8') as f:
        got = {(int(r['pickup_zone_id']), int(r['hour_of_day'])): (int(r['trip_count']), float(r['total_distance']))
               for r in csv.DictReader(f)}

    errors = []
    if expected.keys() != got.keys():
        errors.append(f'group keys differ: {len(expected)} expected, {len(got)} in result')
    worst = 0.0
    for key in expected.keys() & got.keys():
        (c1, s1), (c2, s2) = expected[key], got[key]
        if c1 != c2:
            errors.append(f'{key}: count {c2} != {c1}')
        rel = abs(s1 - s2) / max(abs(s1), 1e-12)
        worst = max(worst, rel)
        if not math.isclose(s1, s2, rel_tol=1e-9, abs_tol=1e-6):
            errors.append(f'{key}: sum {s2} != {s1}')
    total = sum(c for c, _ in expected.values())
    print(f'records={table.num_rows} groups={len(expected)} counted={total} max_relative_sum_error={worst:.2e}')
    if total != table.num_rows:
        errors.append('group counts do not add up to the number of records')
    if errors:
        print('\n'.join(errors[:20]))
        sys.exit(1)
    print('result matches the PyArrow group-by')


if __name__ == '__main__':
    main()
