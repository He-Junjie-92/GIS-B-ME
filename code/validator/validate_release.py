"""Independently validate frozen GIS-B-ME data. Does not certify optimal schedules."""
from pathlib import Path
import argparse,csv,json,hashlib,collections,itertools

def validate(root,full=False):
    errors=[];checks={}
    def require(ok,message):
        if not ok:errors.append(message)
    rows=list(csv.DictReader((root/'metadata/checksums_sha256.csv').open(encoding='utf-8-sig')))
    seen=set()
    for row in rows:
        rel=row['relative_path'];p=(root/rel).resolve()
        require(p.is_relative_to(root),f'path escapes root: {rel}')
        require(rel not in seen,f'duplicate checksum row: {rel}');seen.add(rel)
        if not p.is_file():errors.append(f'missing: {rel}');continue
        require(p.stat().st_size==int(row['bytes']) and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],f'checksum: {rel}')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    require(actual==seen|{'metadata/checksums_sha256.csv','CHECKSUMS.sha256'},'unexpected or unlisted files')
    manifest=list(csv.DictReader((root/'metadata/instance_manifest.csv').open(encoding='utf-8-sig')))
    design={(r['city_code'],int(r['scale']),r['pattern'],int(r['seed'])) for r in manifest}
    require(len(manifest)==135 and design==set(itertools.product(['BJS','SHA','CKG'],[100,500,1000],['CU','CH','CZ'],[12,34,56,78,90])),'factor coverage')
    require(list(dict.fromkeys(r['city_code'] for r in manifest))==['BJS','SHA','CKG'],'city order')
    required={'instance.xlsx','road_matrix.parquet','config.json','README.md','map_preview.png','task_points.geojson','clusters.geojson','used_buildings.geojson','used_building_anchors.geojson'}
    mapping=list(csv.DictReader((root/'metadata/building_id_mapping.csv').open(encoding='utf-8')))
    osm={(r['city_code'],r['building_anchor_id']):r['building_osm_id'] for r in mapping}
    require(len(osm)==3000,'candidate mapping size')
    if full:
        import numpy as np
        import pandas as pd
    tasks_total=0;od_total=0
    for idx,row in enumerate(manifest,1):
        p=root/row['instance_dir'];name=row['instance_id'];city=row['city_code'];n=int(row['scale'])
        require(p.is_dir() and {x.name for x in p.iterdir()}==required,f'{name}: directory structure')
        cfg=json.loads((p/'config.json').read_text(encoding='utf-8'))
        gen=json.loads((root/row['generation_config']).read_text(encoding='utf-8'))
        require(all(cfg[k]==gen[k] for k in cfg.keys()&gen.keys()),f'{name}: shared config fields')
        for k in ['output_root','shared_road_network_path','shared_building_candidates_path']:
            target=(root/cfg[k]).resolve();require(target.is_relative_to(root) and target.exists(),f'{name}: {k}')
        if not full:continue
        with pd.ExcelFile(p/'instance.xlsx') as wb:
            require(len(wb.sheet_names)==14,f'{name}: sheet count')
            ts=wb.parse('TASKS');win=wb.parse('TASK_WINDOWS');bs=wb.parse('BUILDINGS');ns=wb.parse('NODES');c=wb.parse('CONFIG')
        require(len(ts)==n and ts.task_id.nunique()==n,f'{name}: task identifiers')
        require(len(ns)==n+1 and ns.node_id.nunique()==n+1,f'{name}: node identifiers')
        require(set(ts.node_id)==set(ns.loc[ns.node_type=='ELEVATOR','node_id']),f'{name}: task/node join')
        require((ts.service_min==30).all(),f'{name}: service time')
        require(set(win.task_id)==set(ts.task_id),f'{name}: task/window join')
        dates={'RES':list(range(1,16)),'OFF':[1,2,3,4,5,8,9,10,11,12,15],'COM':[1,2,3,4,5,8,9,10,11,12,15],'SCH':[6,7,13,14]}
        windows={k:sorted(zip(g.day,g.ready_time_min,g.due_time_min,g.latest_start_time_min)) for k,g in win.groupby('task_id')}
        for t in ts.itertuples():
            lo,hi=(120,360) if t.building_type=='OFF' else (0,480)
            require(windows.get(t.task_id)==[(d,lo,hi,hi-30) for d in dates[t.building_type]],f'{name}: window {t.task_id}')
            require(t.window_count==len(dates[t.building_type]) and bool(t.is_time_restricted)==(t.building_type!='RES'),f'{name}: window summary {t.task_id}')
            require(t.building_osm_id==osm.get((city,t.building_anchor_id)),f'{name}: OSM identity {t.task_id}')
        counts=ts.groupby('building_anchor_id').size();require(set(counts.index)==set(bs.building_anchor_id),f'{name}: buildings join')
        require((ts.groupby('building_anchor_id').osm_node_id.nunique()==1).all(),f'{name}: shared road access')
        for b in bs.itertuples():
            require(counts[b.building_anchor_id]==b.n_tasks_assigned<=b.estimated_elevator_capacity,f'{name}: capacity {b.building_anchor_id}')
            require(b.building_osm_id==osm.get((city,b.building_anchor_id)),f'{name}: building OSM identity')
        config=dict(zip(c.iloc[:,0],c.iloc[:,1]));require(config['road_network_file']==cfg['shared_road_network_path'],f'{name}: workbook road path')
        od=pd.read_parquet(p/'road_matrix.parquet');a=od.from_node_id;b=od.to_node_id
        require(len(od)==(n+1)**2 and not od.duplicated(['from_node_id','to_node_id']).any(),f'{name}: OD count/duplicates')
        require(set(a)==set(ns.node_id) and set(b)==set(ns.node_id),f'{name}: OD endpoint coverage')
        costs=od[['road_distance_m','road_time_min','road_time_sec']].to_numpy()
        require(np.isfinite(costs).all() and (costs>=0).all(),f'{name}: OD finite/nonnegative')
        require(np.allclose(od.road_time_min,od.road_distance_m/250,rtol=1e-10,atol=1e-8) and np.allclose(od.road_time_sec,od.road_time_min*60),f'{name}: fixed speed')
        require(np.allclose(od.loc[a==b,'road_distance_m'],0),f'{name}: OD diagonal')
        tasks_total+=n;od_total+=len(od)
        if idx%15==0:print(f'Validated {idx}/135',flush=True)
    checks.update(files_hashed=len(rows),instances=len(manifest),full=full,tasks_checked=tasks_total,od_records_checked=od_total)
    return {'passed':not errors,'checks':checks,'errors':errors}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--full',action='store_true')
    args=parser.parse_args();result=validate(args.root.resolve(),args.full)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['passed'] else 1)

if __name__=='__main__':main()
