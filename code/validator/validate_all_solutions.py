"""Validate all published reference solutions and rebuild validation evidence."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import pandas as pd
from validate_solution import validate

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args();root=a.root.resolve()
 table_path=root/'reference_results/instance_reference_results.csv';d=pd.read_csv(table_path);out=root/'validation/reference_solutions';out.mkdir(parents=True,exist_ok=True);rows=[]
 for i,r in enumerate(d.itertuples(index=False),1):
  sp=root/'reference_results'/r.solution_file; report=validate(root/'data/instances'/r.instance_id,sp,1e-5); digest=sha(sp); failures=list(report.get('failures',[]))
  if int(report.get('used_technicians',-1))!=int(r.bks_technicians): failures.append('BKS technician count mismatch')
  if abs(float(report.get('total_travel_time',float('inf')))-float(r.bks_travel_time_min))>1e-5: failures.append('BKS travel reconstruction mismatch')
  if digest!=r.solution_sha256: failures.append('solution SHA-256 mismatch')
  report['valid']=bool(report.get('valid')) and not failures;report['failures']=failures;report['failure_count']=len(failures);report['solution_sha256']=digest;report['dataset_release']=r.dataset_release;report['source_reference_batch']=r.source_reference_batch
  (out/f'{r.instance_id}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  rows.append({k:report[k] for k in ['instance','solution','n_tasks','n_solution_rows','used_technicians','total_travel_time','total_waiting_time','max_daily_work_time','failure_count','valid','solution_sha256']})
  if i%15==0:print(f'Validated {i}/135',flush=True)
 frame=pd.DataFrame(rows);frame.to_csv(root/'validation/reference_solutions_validation.csv',index=False,encoding='utf-8-sig',float_format='%.9f')
 summary={'instances':len(frame),'solution_files':len(list((root/'reference_results/solutions').glob('*.csv'))),'task_rows':int(frame.n_solution_rows.sum()),'passed':int(frame.valid.sum()),'failed':int((~frame.valid).sum()),'K-OPT':int(d.status.eq('K-OPT').sum()),'K-OPEN':int(d.status.eq('K-OPEN').sum()),'gap_1':int(d.gap.eq(1).sum()),'gap_2':int(d.gap.eq(2).sum()),'by_scale_K_OPT':{str(k):int(v) for k,v in d[d.status.eq('K-OPT')].groupby('scale').size().reindex([100,500,1000],fill_value=0).items()},'by_city_K_OPT':{str(k):int(v) for k,v in d[d.status.eq('K-OPT')].groupby('city_id').size().items()},'by_pattern_K_OPT':{str(k):int(v) for k,v in d[d.status.eq('K-OPT')].groupby('cluster_pattern').size().items()}}
 (root/'validation/reference_solutions_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False));raise SystemExit(0 if summary['failed']==0 else 1)
if __name__=='__main__':main()
