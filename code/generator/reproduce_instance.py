"""Regenerate one GIS-B-ME instance from the packaged frozen inputs and compare it."""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--instance-id',required=True)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument('--output-root',type=Path,required=True)
    args=ap.parse_args(); root=args.root.resolve(); out=args.output_root.resolve(); iid=args.instance_id
    manifest=__import__('pandas').read_csv(root/'metadata/instance_manifest.csv').set_index('instance_id')
    if iid not in manifest.index: raise SystemExit(f'Unknown instance: {iid}')
    cfg_path=root/manifest.loc[iid,'generation_config']; cfg=json.loads(cfg_path.read_text(encoding='utf-8'))
    cfg['output_root']=str(out); city=cfg['city_id']; cfg['shared_road_network_path']=str((root/'data/shared/cities'/city/'road_network.graphml').resolve()); cfg['shared_building_candidates_path']=str((root/'data/shared/cities'/city/'building_candidates.geojson').resolve())
    out.mkdir(parents=True,exist_ok=True); resolved=out/f'{iid}.resolved-config.json'; resolved.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    here=Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(here/'generate_gis_b_instance.py'),'--config',str(resolved)],check=True)
    report=out/f'{iid}.comparison.json'
    result=subprocess.run([sys.executable,str(here/'compare_regenerated_instance.py'),'--released',str(root/'data/instances'/iid),'--generated',str(out/iid),'--output',str(report)])
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
