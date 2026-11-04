#!/usr/bin/env python3
"""End-to-end synthetic tests for the C++ programs."""
import argparse, csv, math, subprocess, tempfile
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--serial',required=True); parser.add_argument('--openmp',required=True); parser.add_argument('--cache',required=True); args=parser.parse_args()
    rows=[(161,8,3.45),(161,8,1.55),(161,9,4.0),(-42,23,2.0),(999999,0,7.0)]
    with tempfile.TemporaryDirectory(prefix='crazy-taxi-') as tmp:
        root=Path(tmp); source=root/'trips.csv'; expected=root/'expected.csv'; parallel=root/'parallel.csv'
        with source.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['pickup_zone_id','hour_of_day','trip_distance']);w.writerows(rows)
        out=subprocess.run([args.serial,'--input',str(source),'--output',str(expected)],capture_output=True,text=True)
        if out.returncode: raise AssertionError(out.stderr)
        with expected.open(newline='') as f: result=list(csv.DictReader(f))
        assert [(int(r['pickup_zone_id']),int(r['hour_of_day']),int(r['trip_count'])) for r in result]==[(-42,23,1),(161,8,2),(161,9,1),(999999,0,1)]
        assert math.isclose(float(result[1]['total_distance']),5.0,abs_tol=1e-9)
        assert math.isclose(float(result[1]['average_distance']),2.5,abs_tol=1e-9)
        for threads in (1,2,4,8):
            run=subprocess.run([args.openmp,'--input',str(source),'--output',str(parallel),'--threads',str(threads),'--schedule','guided'],capture_output=True,text=True)
            if run.returncode: raise AssertionError(run.stderr)
            assert parallel.read_bytes()==expected.read_bytes()
        malformed=root/'malformed.csv';malformed.write_text('pickup_zone_id,hour_of_day,trip_distance\n1,24,2\n')
        bad=subprocess.run([args.serial,'--input',str(malformed),'--output',str(root/'bad.csv')],capture_output=True,text=True)
        assert bad.returncode!=0
        empty=root/'empty.csv';empty.write_text('pickup_zone_id,hour_of_day,trip_distance\n')
        empty_out=root/'empty-results.csv'
        assert subprocess.run([args.serial,'--input',str(empty),'--output',str(empty_out)],capture_output=True,text=True).returncode==0
        assert len(list(csv.DictReader(empty_out.open(newline=''))))==0
        assert subprocess.run([args.cache,'--synthetic','1000'],capture_output=True,text=True,check=True).stdout.count('stride=')==4
        selected=subprocess.run([args.cache,'--synthetic','1000','--stride','8'],capture_output=True,text=True,check=True).stdout
        assert selected.count('stride=')==1 and 'stride=8 ' in selected
    print('analytics synthetic tests passed')
if __name__=='__main__':main()
