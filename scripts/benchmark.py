#!/usr/bin/env python3
"""Run repeated serial/OpenMP timings and save reproducible CSV measurements."""
import argparse,csv,statistics,subprocess,tempfile
from pathlib import Path

def run(executable,args):
    result=subprocess.run([str(executable),*map(str,args)],capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stderr.strip() or f'command failed: {executable}')
    values={}
    for line in result.stdout.splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            try: values[key]=float(value)
            except ValueError: pass
    required={'records','loading_ms','aggregation_ms','writing_ms','end_to_end_ms'}
    if not required.issubset(values): raise RuntimeError(f'Unrecognized timing output from {executable}: {result.stdout}')
    return values

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=['dataset','dataset_size_bytes','record_count','implementation','thread_count','schedule','run_number','loading_ms','aggregation_ms','writing_ms','end_to_end_ms','speedup','efficiency','estimated_serial_fraction']
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--serial',type=Path,default=Path('build/serial'));p.add_argument('--openmp',type=Path,default=Path('build/openmp'))
    p.add_argument('--samples-dir',type=Path,default=Path('data/samples'));p.add_argument('--full',type=Path,default=Path('data/processed/taxi_2025_clean.csv'))
    p.add_argument('--output',type=Path,default=Path('results/timings.csv'));p.add_argument('--runs',type=int,default=3);p.add_argument('--threads',default='1,2,4,8');p.add_argument('--schedules',default='static,dynamic,guided');p.add_argument('--smoke',action='store_true')
    a=p.parse_args();
    if a.runs<1 or (not a.smoke and a.runs<3):p.error('use at least three runs for benchmark experiments')
    threads=[int(x) for x in a.threads.split(',')];schedules=a.schedules.split(','); rows=[]
    smoke_temp=None
    output_temp=tempfile.TemporaryDirectory(prefix='crazy-taxi-bench-output-')
    intermediate_dir=Path(output_temp.name)
    if a.smoke:
        smoke_temp=tempfile.TemporaryDirectory(prefix='crazy-taxi-bench-')
        sample=Path(smoke_temp.name)/'small.csv';sample.write_text('pickup_zone_id,hour_of_day,trip_distance\n1,1,1.0\n1,1,2.0\n-3,23,4.0\n',encoding='utf-8')
        datasets=[('synthetic-smoke',sample)]
    else:
        datasets=[('100mb',a.samples_dir/'taxi_100mb.csv'),('500mb',a.samples_dir/'taxi_500mb.csv'),('full',a.full)]
    for name,path in datasets:
        if not path.is_file():raise FileNotFoundError(f'Missing {name} dataset: {path}')
        size=path.stat().st_size
        count=max(0,sum(1 for _ in path.open(encoding='utf-8'))-1)
        serial_runs=[run(a.serial,['--input',path,'--output',intermediate_dir/'serial.csv']) for _ in range(a.runs)]
        serial_median=statistics.median(x['aggregation_ms'] for x in serial_runs)
        for i,m in enumerate(serial_runs,1):rows.append(dict(dataset=name,dataset_size_bytes=size,record_count=int(m['records']),implementation='serial',thread_count=1,schedule='none',run_number=i,loading_ms=m['loading_ms'],aggregation_ms=m['aggregation_ms'],writing_ms=m['writing_ms'],end_to_end_ms=m['end_to_end_ms'],speedup=1,efficiency=1,estimated_serial_fraction=''))
        if int(serial_runs[0]['records'])!=count:raise RuntimeError(f'{name}: record count changed during benchmark')
        for schedule in schedules:
            for thread_count in threads:
                for index in range(1,a.runs+1):
                    m=run(a.openmp,['--input',path,'--output',intermediate_dir/'openmp.csv','--threads',thread_count,'--schedule',schedule])
                    speed=serial_median/m['aggregation_ms'] if m['aggregation_ms'] else 0.0
                    efficiency=speed/thread_count
                    fraction='' if thread_count==1 else (1/speed-1/thread_count)/(1-1/thread_count) if speed else ''
                    rows.append(dict(dataset=name,dataset_size_bytes=size,record_count=int(m['records']),implementation='openmp',thread_count=thread_count,schedule=schedule,run_number=index,loading_ms=m['loading_ms'],aggregation_ms=m['aggregation_ms'],writing_ms=m['writing_ms'],end_to_end_ms=m['end_to_end_ms'],speedup=speed,efficiency=efficiency,estimated_serial_fraction=fraction))
    write_csv(a.output,rows);print(f'Wrote {len(rows)} timing rows to {a.output}')
    if smoke_temp: smoke_temp.cleanup()
    output_temp.cleanup()
if __name__=='__main__':main()
