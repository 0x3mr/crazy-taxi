#!/usr/bin/env python3
"""Compare result CSVs by exact counts and tolerant floating-point sums."""
import argparse,csv,math
from pathlib import Path

def read(path):
    with Path(path).open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f); expected=['pickup_zone_id','hour_of_day','trip_count','total_distance','average_distance']
        if reader.fieldnames!=expected: raise ValueError(f'{path}: unexpected result columns')
        data={}
        for row in reader:
            key=(int(row[expected[0]]),int(row[expected[1]]))
            if key in data: raise ValueError(f'{path}: duplicate group {key}')
            data[key]=(int(row['trip_count']),float(row['total_distance']),float(row['average_distance']))
        if list(data)!=sorted(data): raise ValueError(f'{path}: rows are not sorted')
        return data

def compare(reference,candidate,rel_tol=1e-10,abs_tol=1e-9):
    a,b=read(reference),read(candidate)
    if a.keys()!=b.keys(): raise AssertionError('Group keys differ')
    for key in a:
        if a[key][0]!=b[key][0]: raise AssertionError(f'{key}: trip counts differ')
        for label,x,y in zip(('total distance','average distance'),a[key][1:],b[key][1:]):
            if not math.isclose(x,y,rel_tol=rel_tol,abs_tol=abs_tol): raise AssertionError(f'{key}: {label} differs: {x} vs {y}')

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory(prefix='crazy-taxi-') as d:
        p=Path(d); content='pickup_zone_id,hour_of_day,trip_count,total_distance,average_distance\n-1,2,2,3.00,1.50\n'
        (p/'a').write_text(content);(p/'b').write_text(content.replace('3.00','3.00'))
        compare(p/'a',p/'b')

def main():
    p=argparse.ArgumentParser();p.add_argument('reference',nargs='?');p.add_argument('candidate',nargs='?');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:self_test();print('result validation self-test passed')
    elif a.reference and a.candidate:compare(a.reference,a.candidate);print('results match')
    else:p.error('provide two result files or --self-test')
if __name__=='__main__':main()
