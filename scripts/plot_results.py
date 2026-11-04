#!/usr/bin/env python3
"""Plot median aggregation time, speedup, and efficiency from timings.csv."""
import argparse,csv,statistics
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=Path('results/timings.csv'));p.add_argument('--output-dir',type=Path,default=Path('plots'));a=p.parse_args()
    try:import matplotlib.pyplot as plt
    except ImportError:p.error('matplotlib is required: python -m pip install matplotlib')
    with a.input.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
    grouped={}
    for r in rows:
        if r['implementation']!='openmp':continue
        key=(r['dataset'],r['schedule'],int(r['thread_count']))
        grouped.setdefault(key,[]).append(r)
    datasets=sorted({k[0] for k in grouped});schedules=sorted({k[1] for k in grouped});a.output_dir.mkdir(parents=True,exist_ok=True)
    for dataset in datasets:
        for metric,label,filename in [('aggregation_ms','Aggregation time (ms)','execution_time'),('speedup','Speedup','speedup'),('efficiency','Efficiency','efficiency')]:
            fig,ax=plt.subplots()
            for schedule in schedules:
                keys=sorted((k for k in grouped if k[0]==dataset and k[1]==schedule),key=lambda x:x[2])
                if keys:ax.plot([k[2] for k in keys],[statistics.median(float(r[metric]) for r in grouped[k]) for k in keys],marker='o',label=schedule)
            ax.set(xlabel='OpenMP threads',ylabel=label,title=f'{label}: {dataset} dataset');ax.grid(True,alpha=.3);ax.legend();fig.tight_layout()
            fig.savefig(a.output_dir/f'{dataset}_{filename}.png',dpi=160);plt.close(fig)
    print(f'Plots saved in {a.output_dir}')
if __name__=='__main__':main()
