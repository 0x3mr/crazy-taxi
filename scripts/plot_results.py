#!/usr/bin/env python3
"""Make the report plots from results/summary_*.csv and the experiment logs."""
import argparse
import csv
import re
from pathlib import Path


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def parse_kv(path):
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        pairs = dict(re.findall(r'(\w+)=(\S+)', line))
        if pairs:
            rows.append(pairs)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, default=Path('results'))
    ap.add_argument('--output-dir', type=Path, default=Path('plots'))
    a = ap.parse_args()
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        ap.error('matplotlib is required: python -m pip install matplotlib')
    out = a.output_dir
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'figure.figsize': (6, 4), 'axes.grid': True, 'grid.alpha': 0.3, 'font.size': 10})
    colors = {'static': 'tab:blue', 'dynamic': 'tab:orange', 'guided': 'tab:green'}

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(out / name, dpi=160)
        plt.close(fig)

    scaling = read_csv(a.results / 'summary_scaling.csv')
    threads = sorted({int(r['threads']) for r in scaling})

    def series(ds, sched, key):
        sel = sorted((r for r in scaling if r['dataset'] == ds and r['schedule'] == sched), key=lambda r: int(r['threads']))
        return [int(r['threads']) for r in sel], [float(r[key]) for r in sel]

    # 1. full dataset, static: speedup of each phase against ideal
    fig, ax = plt.subplots()
    ax.plot(threads, threads, 'k--', lw=1, label='ideal (S = p)')
    for key, label in (('parse', 'parse (tasks)'), ('aggregation', 'aggregation (parallel for)'), ('end_to_end', 'end-to-end')):
        x, y = series('full', 'static', f'{key}_speedup')
        ax.plot(x, y, marker='o', label=label)
    ax.axvline(6, color='grey', lw=0.8, ls=':')
    ax.text(6.1, 0.5, '6 physical cores', fontsize=8, color='grey')
    ax.set(xlabel='threads p', ylabel='speedup S = T_S / T_p', title='Speedup by phase, full dataset (static)', xticks=threads)
    ax.legend()
    save(fig, 'speedup_phases_full.png')

    # 2./3. end-to-end speedup and efficiency per dataset and schedule
    for key, ylabel, name in (('end_to_end_speedup', 'speedup', 'speedup'), ('end_to_end_efficiency', 'efficiency E = S / p', 'efficiency')):
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
        for ax, ds in zip(axes, ('100mb', '250mb', 'full')):
            if key.endswith('speedup'):
                ax.plot(threads, threads, 'k--', lw=1, label='ideal')
            for sched, c in colors.items():
                x, y = series(ds, sched, key)
                if x:
                    ax.plot(x, y, marker='o', color=c, label=sched)
            ax.set(title=ds, xlabel='threads p', xticks=threads)
        axes[0].set_ylabel(f'end-to-end {ylabel}')
        axes[0].legend()
        save(fig, f'end_to_end_{name}.png')

    # 4. where the time goes (full, static)
    sel = sorted((r for r in scaling if r['dataset'] == 'full' and r['schedule'] == 'static'), key=lambda r: int(r['threads']))
    timings = read_csv(a.results / 'timings.csv')

    def phase_median(p, key):
        import statistics
        vals = [float(r[key]) for r in timings if r['experiment'] == 'scaling' and r['dataset'] == 'full'
                and ((p == 0 and r['implementation'] == 'serial') or
                     (p > 0 and r['implementation'] == 'openmp' and r['schedule'] == 'static' and int(r['thread_count']) == p))]
        return statistics.median(vals)

    labels = ['serial'] + [f'p={int(r["threads"])}' for r in sel]
    ps = [0] + [int(r['threads']) for r in sel]
    fig, ax = plt.subplots(figsize=(7, 4))
    bottom = [0.0] * len(ps)
    for key, label in (('read_ms', 'read file'), ('parse_ms', 'parse'), ('aggregation_ms', 'aggregate'), ('writing_ms', 'write')):
        vals = [phase_median(p, key) for p in ps]
        ax.bar(labels, vals, bottom=bottom, label=label)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set(ylabel='median time (ms)', title='Time per phase, full dataset (static)')
    ax.legend()
    save(fig, 'phase_breakdown_full.png')

    # 5. aggregation strategies
    path = a.results / 'summary_strategy.csv'
    if path.exists():
        rows = read_csv(path)
        ts = [c for c in rows[0] if c != 'strategy']
        fig, ax = plt.subplots()
        for r in rows:
            xs = [int(t) for t in ts if r[t]]
            ys = [float(r[t]) for t in ts if r[t]]
            ax.plot(xs, ys, marker='o', ls='--' if r['strategy'] == 'serial map' else '-', label=r['strategy'])
        ax.set_yscale('log')
        ax.set(xlabel='threads p', ylabel='aggregation time (ms, log)', title='Aggregation strategies, 100 MB sample',
               xticks=[int(t) for t in ts])
        ax.legend(fontsize=8)
        save(fig, 'strategies_100mb.png')

    # 6. chunk size
    path = a.results / 'summary_chunk.csv'
    if path.exists():
        rows = read_csv(path)
        chunks = sorted({int(r['chunk']) for r in rows})
        fig, ax = plt.subplots()
        width = 0.27
        for i, sched in enumerate(('static', 'dynamic', 'guided')):
            ys = [next(float(r['aggregation_ms']) for r in rows if r['schedule'] == sched and int(r['chunk']) == c) for c in chunks]
            ax.bar([j + (i - 1) * width for j in range(len(chunks))], ys, width, label=sched, color=colors[sched])
        ax.set_xticks(range(len(chunks)), [str(c) for c in chunks])
        ax.set_yscale('log')
        ax.set(xlabel='chunk size', ylabel='aggregation time (ms, log)', title=f'Chunk size, 100 MB sample, {rows[0]["threads"]} threads')
        ax.legend()
        save(fig, 'chunk_size_100mb.png')

    # 7. stride experiment
    path = a.results / 'cache_test.txt'
    if path.exists():
        rows = [r for r in parse_kv(path) if r.get('test') == 'stride']
        fig, ax = plt.subplots()
        ax.plot([int(r['stride']) for r in rows], [float(r['ns_per_element']) for r in rows], marker='o')
        ax.set_xscale('log', base=2)
        ax.axvline(8, color='grey', lw=0.8, ls=':')
        ax.text(8.5, ax.get_ylim()[1] * 0.9, '8 doubles = one 64 B line', fontsize=8, color='grey')
        ax.set(xlabel='stride (elements)', ylabel='ns per element', title='Stride test on trip distances (47.3M doubles)')
        save(fig, 'cache_stride.png')

    # 8. false sharing
    path = a.results / 'false_sharing.txt'
    if path.exists():
        rows = parse_kv(path)
        fig, ax = plt.subplots()
        x = [int(r['threads']) for r in rows]
        for key, label in (('adjacent_ms', 'adjacent counters (shared line)'), ('padded_ms', 'padded to 64 B'), ('private_ms', 'private + reduction')):
            ax.plot(x, [float(r[key]) for r in rows], marker='o', label=label)
        ax.set(xlabel='threads p', ylabel='time (ms)', title='Per-thread counters: false sharing', xticks=x)
        ax.legend()
        save(fig, 'false_sharing.png')

    print(f'Plots saved in {out}')


if __name__ == '__main__':
    main()
