#!/usr/bin/env python3
"""Run the serial and OpenMP programs repeatedly and store one CSV row per run.

Experiments (all with --runs repetitions):
  scaling   serial + OpenMP 'local' strategy, every schedule x thread count,
            on the 100 MB, 250 MB and full datasets (dynamic uses chunk 4096,
            because chunk 1 costs about 2.5 us per iteration in libgomp)
  strategy  every aggregation strategy (local/reduction/atomic/critical/map),
            static schedule, on the 100 MB sample
  chunk     static, dynamic and guided with chunk sizes 1..65536, 100 MB sample
            (chunk 1 is repeated only 3 times because dynamic,1 is very slow)
Medians, speedup and efficiency are computed afterwards by summarize.py.
"""
import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

FIELDS = ['experiment', 'dataset', 'dataset_size_bytes', 'record_count', 'implementation', 'strategy',
          'thread_count', 'schedule', 'chunk', 'run_number', 'read_ms', 'parse_ms', 'loading_ms',
          'aggregation_ms', 'writing_ms', 'end_to_end_ms']
TIMES = ['read_ms', 'parse_ms', 'loading_ms', 'aggregation_ms', 'writing_ms', 'end_to_end_ms']


def run(executable, args):
    result = subprocess.run([str(executable), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'command failed: {executable}')
    values = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition('=')
        try:
            values[key] = float(value)
        except ValueError:
            pass
    if not {'records', *TIMES} <= values.keys():
        raise RuntimeError(f'Unrecognized timing output from {executable}: {result.stdout}')
    return values


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--serial', type=Path, default=Path('build/serial'))
    p.add_argument('--openmp', type=Path, default=Path('build/openmp'))
    p.add_argument('--samples-dir', type=Path, default=Path('data/samples'))
    p.add_argument('--full', type=Path, default=Path('data/processed/taxi_2025_clean.csv'))
    p.add_argument('--output', type=Path, default=Path('results/timings.csv'))
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--threads', default='1,2,4,8,12')
    p.add_argument('--schedules', default='static,dynamic,guided')
    p.add_argument('--experiments', default='scaling,strategy,chunk')
    p.add_argument('--smoke', action='store_true', help='tiny synthetic input, only checks that the runner works')
    a = p.parse_args()
    if a.runs < 1 or (not a.smoke and a.runs < 3):
        p.error('use at least three runs for benchmark experiments')
    threads = [int(x) for x in a.threads.split(',')]
    schedules = a.schedules.split(',')
    experiments = set(a.experiments.split(','))

    with tempfile.TemporaryDirectory(prefix='crazy-taxi-bench-') as tmp:
        tmp = Path(tmp)
        if a.smoke:
            sample = tmp / 'small.csv'
            sample.write_text('pickup_zone_id,hour_of_day,trip_distance\n1,1,1.0\n1,1,2.0\n3,23,4.0\n', encoding='utf-8')
            datasets = {'smoke': sample}
            threads, schedules, experiments = [1, 2], ['static'], {'scaling', 'strategy'}
            strategy_set, chunk_set = 'smoke', 'smoke'
        else:
            datasets = {'100mb': a.samples_dir / 'taxi_100mb.csv', '250mb': a.samples_dir / 'taxi_250mb.csv', 'full': a.full}
            strategy_set, chunk_set = '100mb', '100mb'
        for name, path in datasets.items():
            if not path.is_file():
                raise FileNotFoundError(f'Missing {name} dataset: {path}')

        rows = []

        def record(experiment, dataset, impl, strategy, t, schedule, chunk, args, exe, runs=None):
            path = datasets[dataset]
            for i in range(1, (runs or a.runs) + 1):
                m = run(exe, ['--input', path, '--output', tmp / 'out.csv', *args])
                rows.append(dict(experiment=experiment, dataset=dataset, dataset_size_bytes=path.stat().st_size,
                                 record_count=int(m['records']), implementation=impl, strategy=strategy,
                                 thread_count=t, schedule=schedule, chunk=chunk, run_number=i,
                                 **{k: m[k] for k in TIMES}))
            last = rows[-1]
            print(f"{experiment:8} {dataset:6} {impl:6} {strategy:9} t={t:<2} {schedule:7} chunk={chunk:<5} "
                  f"parse={last['parse_ms']:.0f} agg={last['aggregation_ms']:.1f} total={last['end_to_end_ms']:.0f} ms", flush=True)

        if 'scaling' in experiments:
            for name in datasets:
                record('scaling', name, 'serial', 'dense', 1, 'none', 0, [], a.serial)
                for schedule in schedules:
                    chunk = 4096 if schedule == 'dynamic' else 0
                    for t in threads:
                        record('scaling', name, 'openmp', 'local', t, schedule, chunk,
                               ['--threads', t, '--schedule', schedule, '--chunk', chunk], a.openmp)
        if 'strategy' in experiments:
            record('strategy', strategy_set, 'serial', 'map', 1, 'none', 0, ['--strategy', 'map'], a.serial)
            for strategy in ('local', 'reduction', 'atomic', 'critical', 'map'):
                for t in threads:
                    record('strategy', strategy_set, 'openmp', strategy, t, 'static', 0,
                           ['--threads', t, '--schedule', 'static', '--strategy', strategy], a.openmp)
        if 'chunk' in experiments:
            t = max(x for x in threads if x <= 8)
            for schedule in ('static', 'dynamic', 'guided'):
                for chunk in (1, 64, 1024, 4096, 65536):
                    record('chunk', chunk_set, 'openmp', 'local', t, schedule, chunk,
                           ['--threads', t, '--schedule', schedule, '--chunk', chunk], a.openmp,
                           runs=min(a.runs, 3) if chunk == 1 else None)

    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'Wrote {len(rows)} timing rows to {a.output}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, FileNotFoundError) as e:
        sys.exit(f'benchmark: {e}')
