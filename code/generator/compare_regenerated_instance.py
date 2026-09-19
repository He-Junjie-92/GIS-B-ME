"""Compare regenerated and released GIS-B-ME instances by canonical content."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd

CORE_SHEETS=['CLUSTERS','TECHNICIANS','TASKS','BUILDINGS','TASK_WINDOWS','VALIDATION','GIS_VALIDATION','BUILDING_STATS','CAPACITY_RULES','ELEVATOR_DISTRIBUTION','README']
GEOJSON=['task_points.geojson','clusters.geojson','used_buildings.geojson','used_building_anchors.geojson']

def frame_equal(a,b):
    if a.shape!=b.shape or list(a.columns)!=list(b.columns): return False
    for c in a.columns:
        x,y=a[c],b[c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            if not np.isclose(pd.to_numeric(x,errors='coerce'),pd.to_numeric(y,errors='coerce'),equal_nan=True,rtol=1e-10,atol=1e-8).all(): return False
        elif not x.fillna('<NA>').astype(str).equals(y.fillna('<NA>').astype(str)): return False
    return True

def compare(released:Path,generated:Path):
    checks={}
    for s in CORE_SHEETS:
        checks['xlsx:'+s]=frame_equal(pd.read_excel(released/'instance.xlsx',sheet_name=s),pd.read_excel(generated/'instance.xlsx',sheet_name=s))
    na=pd.read_excel(released/'instance.xlsx',sheet_name='NODES'); nb=pd.read_excel(generated/'instance.xlsx',sheet_name='NODES')
    for n in (na,nb): n.loc[n.node_type.astype(str).str.upper().eq('STATION'),'snap_distance_m']=0.0
    checks['xlsx:NODES_canonical']=frame_equal(na,nb)
    ra=pd.read_excel(released/'instance.xlsx',sheet_name='ROAD_NETWORK'); rb=pd.read_excel(generated/'instance.xlsx',sheet_name='ROAD_NETWORK')
    checks['xlsx:ROAD_NETWORK_canonical']=set(ra.metric.astype(str))==set(rb.metric.astype(str))
    a=pd.read_excel(released/'instance.xlsx',sheet_name='CONFIG'); b=pd.read_excel(generated/'instance.xlsx',sheet_name='CONFIG')
    b.loc[b.param.astype(str).eq('v2_pilot_candidate_pool'),'param']='fixed_candidate_pool'
    skip={'osm_data_date','road_network_file'}
    a=a[~a.param.astype(str).isin(skip)].set_index('param'); b=b[~b.param.astype(str).isin(skip)].set_index('param')
    common=sorted(set(a.index)&set(b.index)); checks['xlsx:CONFIG_canonical']=frame_equal(a.loc[common].reset_index(),b.loc[common].reset_index())
    ma=pd.read_parquet(released/'road_matrix.parquet').sort_values(['from_node_id','to_node_id']).reset_index(drop=True)
    mb=pd.read_parquet(generated/'road_matrix.parquet').sort_values(['from_node_id','to_node_id']).reset_index(drop=True)
    ma['routing_status']=ma.routing_status.astype(str).str.upper(); mb['routing_status']=mb.routing_status.astype(str).str.upper(); checks['road_matrix']=frame_equal(ma,mb)
    def norm_geo(path):
        obj=json.loads(path.read_text(encoding='utf-8'))
        def norm(v):
            if isinstance(v,float): return round(v,5)
            if isinstance(v,list): return [norm(x) for x in v]
            if isinstance(v,dict): return {k:norm(x) for k,x in sorted(v.items())}
            return v
        for f in obj.get('features',[]):
            pr=f.get('properties',{});
            if str(pr.get('node_type','')).upper()=='STATION': pr['snap_distance_m']=0.0
        return norm(obj)
    for fn in GEOJSON: checks['geojson:'+fn]=norm_geo(released/fn)==norm_geo(generated/fn)
    ca=json.loads((released/'config.json').read_text(encoding='utf-8')); cb=json.loads((generated/'config.json').read_text(encoding='utf-8'))
    skipkeys={'output_root','shared_road_network_path','shared_building_candidates_path','restricted_tasks','restricted_task_ratio','service_windows','time_window_design'}
    common=(set(ca)&set(cb))-skipkeys
    checks['config_core']=all(ca[k]==cb[k] for k in common) and not ((set(cb)-set(ca))-skipkeys)
    return {'instance_id':released.name,'passed':all(checks.values()),'checks':checks,'excluded_release_artifacts':['README.md','map_preview.png'],'normalized_metadata':['osm_data_date','road_network_file','output/shared paths','v2_pilot_candidate_pool -> fixed_candidate_pool','derived v3 service-window summary fields']}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--released',type=Path,required=True); ap.add_argument('--generated',type=Path,required=True); ap.add_argument('--output',type=Path); a=ap.parse_args(); r=compare(a.released,a.generated); text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text+'\n',encoding='utf-8')
    print(text); raise SystemExit(0 if r['passed'] else 1)
if __name__=='__main__':main()



