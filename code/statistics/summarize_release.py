"""Recompute compact descriptive and reference-result summaries for GIS-B-ME."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd


def summarize(root: Path) -> dict:
    manifest=pd.read_csv(root/'metadata/instance_manifest.csv')
    task_parts=[]; building_rows=[]
    for r in manifest.itertuples(index=False):
        p=root/str(r.instance_dir)/'instance.xlsx'
        tasks=pd.read_excel(p,sheet_name='TASKS',usecols=['task_id','building_anchor_id','building_type'])
        buildings=pd.read_excel(p,sheet_name='BUILDINGS',usecols=['building_anchor_id','n_tasks_assigned'])
        tasks['instance_id']=r.instance_id; task_parts.append(tasks)
        building_rows.append({'instance_id':r.instance_id,'scale':int(r.scale),'used_buildings':len(buildings),'multi_task_buildings':int((buildings.n_tasks_assigned>1).sum()),'tasks_per_building':len(tasks)/len(buildings)})
    tasks=pd.concat(task_parts,ignore_index=True); b=pd.DataFrame(building_rows)
    counts=tasks.building_type.value_counts().reindex(['RES','OFF','COM','SCH'],fill_value=0)
    result={
      'instances':int(len(manifest)),'tasks':int(len(tasks)),
      'instances_by_scale':{str(k):int(v) for k,v in manifest.groupby('scale').size().items()},
      'tasks_by_type':{k:int(v) for k,v in counts.items()},
      'pooled_task_share_by_type':{k:float(v/len(tasks)) for k,v in counts.items()},
      'mean_tasks_per_used_building_across_instances':float(b.tasks_per_building.mean()),
      'pooled_used_building_records':int(b.used_buildings.sum()),
      'pooled_multi_task_building_records':int(b.multi_task_buildings.sum()),
    }
    rp=root/'reference_results/instance_reference_results.csv'
    if rp.exists():
        ref=pd.read_csv(rp)
        result['reference_results']={
          'rows':int(len(ref)),'K-OPT':int(ref.status.eq('K-OPT').sum()),'K-OPEN':int(ref.status.eq('K-OPEN').sum()),
          'gap_counts':{str(int(k)):int(v) for k,v in ref.groupby('gap').size().items()},
          'k_opt_by_scale':{str(k):int(v) for k,v in ref[ref.status.eq('K-OPT')].groupby('scale').size().reindex([100,500,1000],fill_value=0).items()},
          'validator_pass':int(ref.validator_status.eq('PASS').sum())
        }
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); ap.add_argument('--output',type=Path)
    a=ap.parse_args(); result=summarize(a.root.resolve()); text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output: a.output.write_text(text+'\n',encoding='utf-8')
    print(text)

if __name__=='__main__': main()
