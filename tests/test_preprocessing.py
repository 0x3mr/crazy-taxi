#!/usr/bin/env python3
"""Synthetic Parquet preprocessing test; install preprocessing requirements to run."""
import csv, tempfile
from datetime import datetime
from pathlib import Path

def main():
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'preprocessing'))
    from generate_samples import make_sample
    with tempfile.TemporaryDirectory(prefix='crazy-taxi-samples-') as tmp:
        root=Path(tmp); source=root/'clean.csv'
        with source.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f,lineterminator='\n');w.writerow(['pickup_zone_id','hour_of_day','trip_distance'])
            for i in range(100):w.writerow([i%7,i%24,f'{i+0.5:.1f}'])
        first=root/'first.csv'; second=root/'second.csv'
        count1,size1=make_sample(source,first,300);count2,size2=make_sample(source,second,300)
        assert first.read_bytes()==second.read_bytes() and count1==count2 and size1==size2 and 0<count1<100
    print('sample generation synthetic test passed')
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print('SKIPPED: PyArrow is not installed; install preprocessing/requirements.txt')
        return
    from prepare_taxi import MONTHS,prepare
    with tempfile.TemporaryDirectory(prefix='crazy-taxi-prep-') as tmp:
        root=Path(tmp); raw=root/'raw';raw.mkdir();out=root/'clean.csv'
        d=datetime
        # one row per rule, plus two valid rows where the second is an exact duplicate
        vals=[d(2025,1,1,8),None,d(2009,1,1,9),d(2025,1,1,10),d(2025,1,1,11),d(2025,1,1,12),d(2025,1,1,13),d(2025,1,1,8),d(2025,1,1,23)]
        zones=[161,2,3,None,4,5,300,161,7]
        dist=[3.45,1.0,2.0,2.0,0.0,250.0,1.0,3.45,float('nan')]
        table=pa.table({'tpep_pickup_datetime':pa.array(vals,type=pa.timestamp('us')),'PULocationID':pa.array(zones,pa.int32()),'trip_distance':dist})
        for name in MONTHS:pq.write_table(table if name==MONTHS[0] else table.slice(0,0),raw/name)
        stats=prepare(raw,out,100.0)
        assert stats['original_record_count']==9 and stats['final_record_count']==1 and stats['discarded_record_count']==8, stats
        assert stats['discarded_by_reason']=={'invalid_timestamp':1,'out_of_period':1,'invalid_zone':2,
                                             'invalid_distance':2,'distance_outlier':1,'duplicate':1}, stats['discarded_by_reason']
        with out.open(newline='') as f: rows=list(csv.reader(f))
        assert rows==[['pickup_zone_id','hour_of_day','trip_distance'],['161','8','3.45']], rows
        assert out.with_suffix('.stats.json').is_file()
    print('preprocessing synthetic Parquet test passed')
if __name__=='__main__':main()
