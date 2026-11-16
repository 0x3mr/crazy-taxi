#!/usr/bin/env python3
"""Turn results/timings.csv into median tables with speedup, efficiency and serial fraction.

For every metric (parse, aggregation, end-to-end):
  S = median T_serial / median T_p        E = S / p
  f = (1/S - 1/p) / (1 - 1/p)             (Karp-Flatt estimate, p > 1)
For end-to-end runs we also report the serial share s of the *parallel* run
(file read + result write, which are not parallelised) and Gustafson's scaled
speedup p - (p - 1) * s.
"""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

METRICS = {'parse': 'parse_ms', 'aggregation': 'aggregation_ms', 'end_to_end': 'end_to_end_ms'}


def med(rows, key):
    return statistics.median(float(r[key]) for r in rows)


def karp_flatt(s, p):
    return (1 / s - 1 / p) / (1 - 1 / p) if p > 1 and s > 0 else None


def fmt(x, digits=3):
    return '' if x is None else f'{x:.{digits}f}'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--input', type=Path, default=Path('results/timings.csv'))
    ap.add_argument('--output-dir', type=Path, default=Path('results'))
    a = ap.parse_args()
    with a.input.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    groups = defaultdict(list)
    for r in rows:
        groups[(r['experiment'], r['dataset'], r['implementation'], r['strategy'], int(r['thread_count']),
                r['schedule'], int(r['chunk']))].append(r)

    # --- scaling ---------------------------------------------------------------
    scaling = []
    for (exp, ds, impl, strat, p, sched, chunk), rs in sorted(groups.items()):
        if exp != 'scaling' or impl != 'openmp':
            continue
        base = groups[('scaling', ds, 'serial', 'dense', 1, 'none', 0)]
        row = dict(dataset=ds, records=rs[0]['record_count'], schedule=sched, threads=p, runs=len(rs))
        for name, key in METRICS.items():
            ts, tp = med(base, key), med(rs, key)
            s = ts / tp
            row[f'{name}_serial_ms'] = round(ts, 2)
            row[f'{name}_ms'] = round(tp, 2)
            row[f'{name}_speedup'] = round(s, 3)
            row[f'{name}_efficiency'] = round(s / p, 3)
            row[f'{name}_serial_fraction'] = fmt(karp_flatt(s, p), 4)
        serial_part = med(rs, 'read_ms') + med(rs, 'writing_ms')
        share = serial_part / med(rs, 'end_to_end_ms')
        row['parallel_run_serial_share'] = round(share, 4)
        row['gustafson_scaled_speedup'] = round(p - (p - 1) * share, 3)
        row['amdahl_limit'] = round(1 / (serial_part / med(base, 'end_to_end_ms')), 2)
        scaling.append(row)
    out = a.output_dir / 'summary_scaling.csv'
    with out.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(scaling[0]))
        w.writeheader()
        w.writerows(scaling)

    md = ['# Benchmark summary', '', f'Source: `{a.input.as_posix()}` (median of {scaling[0]["runs"]} runs per cell).', '']
    for ds in ('100mb', '250mb', 'full'):
        sel = [r for r in scaling if r['dataset'] == ds]
        if not sel:
            continue
        b = sel[0]
        md += [f'## {ds} ({int(b["records"]):,} records)', '',
               f'Serial: parse {b["parse_serial_ms"]:.0f} ms, aggregation {b["aggregation_serial_ms"]:.1f} ms, '
               f'end-to-end {b["end_to_end_serial_ms"]:.0f} ms', '',
               '| schedule | p | parse ms | S | agg ms | S | end-to-end ms | S | E | f | Gustafson |',
               '|---|---|---|---|---|---|---|---|---|---|---|']
        for r in sel:
            md.append(f'| {r["schedule"]} | {r["threads"]} | {r["parse_ms"]:.0f} | {r["parse_speedup"]:.2f} | '
                      f'{r["aggregation_ms"]:.1f} | {r["aggregation_speedup"]:.2f} | {r["end_to_end_ms"]:.0f} | '
                      f'{r["end_to_end_speedup"]:.2f} | {r["end_to_end_efficiency"]:.2f} | '
                      f'{r["end_to_end_serial_fraction"] or "-"} | {r["gustafson_scaled_speedup"]:.2f} |')
        md.append('')

    # --- strategies ------------------------------------------------------------
    strat = defaultdict(dict)
    for (exp, ds, impl, s, p, sched, chunk), rs in groups.items():
        if exp == 'strategy':
            label = 'serial map' if impl == 'serial' else s
            strat[label][p] = med(rs, 'aggregation_ms')
    if strat:
        threads = sorted({p for d in strat.values() for p in d})
        order = [k for k in ('serial map', 'map', 'critical', 'atomic', 'reduction', 'local') if k in strat]
        md += ['## Aggregation strategies (100mb, static, aggregation ms)', '',
               '| strategy | ' + ' | '.join(f'p={p}' for p in threads) + ' |', '|---|' + '---|' * len(threads)]
        for k in order:
            md.append(f'| {k} | ' + ' | '.join(fmt(strat[k].get(p), 1) for p in threads) + ' |')
        md.append('')
        with (a.output_dir / 'summary_strategy.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['strategy', *threads])
            for k in order:
                w.writerow([k, *[fmt(strat[k].get(p), 2) for p in threads]])

    # --- chunk sizes -----------------------------------------------------------
    chunk_rows = sorted((sched, chunk, p, med(rs, 'aggregation_ms'))
                        for (exp, ds, impl, s, p, sched, chunk), rs in groups.items() if exp == 'chunk')
    if chunk_rows:
        md += [f'## Schedule chunk size (100mb, {chunk_rows[0][2]} threads, aggregation ms)', '',
               '| schedule | chunk | aggregation ms |', '|---|---|---|']
        md += [f'| {s} | {c} | {t:.1f} |' for s, c, _, t in chunk_rows]
        md.append('')
        with (a.output_dir / 'summary_chunk.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['schedule', 'chunk', 'threads', 'aggregation_ms'])
            w.writerows([(s, c, p, round(t, 2)) for s, c, p, t in chunk_rows])

    (a.output_dir / 'summary.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(f'Wrote {out}, summary_strategy.csv, summary_chunk.csv and summary.md in {a.output_dir}')


if __name__ == '__main__':
    main()
