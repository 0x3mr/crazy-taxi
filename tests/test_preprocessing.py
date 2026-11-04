#!/usr/bin/env python3
"""Synthetic Parquet preprocessing test; install preprocessing requirements to run."""
import csv, tempfile
from datetime import datetime
from pathlib import Path
from unittest import SkipTest

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
        vals=[datetime(2025,1,1,8),None,datetime(2025,1,1,9),datetime(2025,1,1,10),datetime(2025,1,1,11)]
        zones=[161,2,None,3,4];dist=[3.45,1.0,2.0,0.0,float('inf')]
        table=pa.table({'tpep_pickup_datetime':pa.array(vals,type=pa.timestamp('us')),'PULocationID':zones,'trip_distance':dist})
        for name in MONTHS:pq.write_table(table if name==MONTHS[0] else table.slice(0,0),raw/name)
        stats=prepare(raw,out,2)
        assert stats['original_record_count']==5 and stats['valid_record_count']==1 and stats['discarded_record_count']==4
        assert stats['discarded_by_reason']=={'invalid_timestamp':1,'invalid_zone':1,'invalid_distance':2}
        with out.open(newline='') as f: rows=list(csv.reader(f))
        assert rows==[['pickup_zone_id','hour_of_day','trip_distance'],['161','8','3.4500000000000002']]
        assert out.with_suffix('.stats.json').is_file()
    print('preprocessing synthetic Parquet test passed')
if __name__=='__main__':main()
