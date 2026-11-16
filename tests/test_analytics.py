#!/usr/bin/env python3
"""End-to-end synthetic tests for the C++ programs."""
import argparse, csv, math, random, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_results import compare

STRATEGIES = ['local', 'reduction', 'atomic', 'critical', 'map']


def run(cmd):
    out = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if out.returncode:
        raise AssertionError(f'{cmd[0]} failed: {out.stderr}')
    return out.stdout


def write_trips(path, rows):
    with path.open('w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['pickup_zone_id', 'hour_of_day', 'trip_distance'])
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--serial', required=True); p.add_argument('--openmp', required=True); p.add_argument('--cache', required=True)
    p.add_argument('--openmp-enabled', default='1')
    args = p.parse_args()
    thread_counts = (1, 2, 4, 8) if args.openmp_enabled.lower() in ('1', 'on', 'true', 'yes') else (1,)

    with tempfile.TemporaryDirectory(prefix='crazy-taxi-') as tmp:
        root = Path(tmp)

        # Hand-checked case. Zones -42 and 999999 make the range too wide for the
        # dense table, so this also covers the std::map fallback.
        source = root / 'trips.csv'; expected = root / 'expected.csv'; parallel = root / 'parallel.csv'
        write_trips(source, [(161, 8, 3.45), (161, 8, 1.55), (161, 9, 4.0), (-42, 23, 2.0), (999999, 0, 7.0)])
        run([args.serial, '--input', source, '--output', expected])
        with expected.open(newline='') as f: result = list(csv.DictReader(f))
        assert [(int(r['pickup_zone_id']), int(r['hour_of_day']), int(r['trip_count'])) for r in result] == [(-42, 23, 1), (161, 8, 2), (161, 9, 1), (999999, 0, 1)]
        assert math.isclose(float(result[1]['total_distance']), 5.0, abs_tol=1e-9)
        assert math.isclose(float(result[1]['average_distance']), 2.5, abs_tol=1e-9)
        for threads in thread_counts:
            run([args.openmp, '--input', source, '--output', parallel, '--threads', threads, '--schedule', 'guided'])
            assert parallel.read_bytes() == expected.read_bytes()

        # Random data in the real zone range (dense path). Every strategy, schedule
        # and thread count must agree with the serial map-based result.
        rng = random.Random(7)
        rows = [(rng.randint(1, 265), rng.randint(0, 23), round(rng.uniform(0.01, 30), 2)) for _ in range(20000)]
        big = root / 'big.csv'; write_trips(big, rows)
        ref = root / 'ref.csv'
        run([args.serial, '--input', big, '--output', ref, '--strategy', 'map'])
        dense = root / 'dense.csv'
        run([args.serial, '--input', big, '--output', dense])
        compare(ref, dense)
        with ref.open(newline='') as f:
            assert sum(int(r['trip_count']) for r in csv.DictReader(f)) == len(rows)
        out = root / 'omp.csv'
        for strategy in STRATEGIES:
            for schedule in ('static', 'dynamic', 'guided'):
                for threads in thread_counts:
                    run([args.openmp, '--input', big, '--output', out, '--threads', threads,
                         '--schedule', schedule, '--strategy', strategy, '--chunk', 64])
                    compare(ref, out)
        # many more parse tasks than lines per task, and a file without a final newline
        nonl = root / 'nonl.csv'; nonl.write_text(big.read_text().rstrip('\n'))
        run([args.openmp, '--input', nonl, '--output', out, '--threads', thread_counts[-1], '--parse-tasks', 5000])
        compare(ref, out)

        # Bad input must fail with the right line number, also in the parallel parser.
        malformed = root / 'malformed.csv'
        malformed.write_text('pickup_zone_id,hour_of_day,trip_distance\n1,2,3\n1,2,4\n1,24,2\n')
        for exe in (args.serial, args.openmp):
            bad = subprocess.run([exe, '--input', malformed, '--output', root / 'bad.csv'], capture_output=True, text=True)
            assert bad.returncode != 0 and 'line 4' in bad.stderr, bad.stderr
        for text in ('1,2\n', '1,2,3,4\n', 'a,2,3\n', '1,2,abc\n', '1,2,-1\n', '1,2,3x\n'):
            malformed.write_text('pickup_zone_id,hour_of_day,trip_distance\n' + text)
            assert subprocess.run([args.serial, '--input', malformed, '--output', root / 'bad.csv'], capture_output=True).returncode != 0, text
        wrong_header = root / 'header.csv'; wrong_header.write_text('a,b,c\n1,2,3\n')
        assert subprocess.run([args.serial, '--input', wrong_header, '--output', root / 'bad.csv'], capture_output=True).returncode != 0

        empty = root / 'empty.csv'; empty.write_text('pickup_zone_id,hour_of_day,trip_distance\n')
        empty_out = root / 'empty-results.csv'
        run([args.serial, '--input', empty, '--output', empty_out])
        assert len(list(csv.DictReader(empty_out.open(newline='')))) == 0
        run([args.openmp, '--input', empty, '--output', empty_out, '--threads', thread_counts[-1]])
        assert len(list(csv.DictReader(empty_out.open(newline='')))) == 0

        cache = run([args.cache, '--synthetic', '1000'])
        assert cache.count('test=stride') == 9 and cache.count('test=layout') == 2
        selected = run([args.cache, '--synthetic', '1000', '--stride', '8'])
        assert selected.count('test=stride') == 1 and 'stride=8 ' in selected and 'layout' not in selected
    print('analytics synthetic tests passed')


if __name__ == '__main__':
    main()
