"""Read-only source inventories, not source equivalence or extraction."""
import ee,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_component_audit_20261104';ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
sources={'landscan':'projects/sat-io/open-datasets/ORNL/LANDSCAN_GLOBAL','ghs_2023':'JRC/GHSL/P2023A/GHS_POP','ghs_2016':'JRC/GHSL/P2016/POP_GPW_GLOBE_V1','ghs_2019':'JRC/GHSL/P2019A/GHS_POP'};out={}
for name,asset in sources.items():
 try:
  c=ee.ImageCollection(asset);out[name]={'asset':asset,'collection_metadata':ee.data.getAsset(asset),'count':c.size().getInfo(),'indices':c.aggregate_array('system:index').getInfo(),'times':c.aggregate_array('system:time_start').getInfo(),'first':c.first().getInfo()};print(name,out[name]['count'],out[name]['indices'],flush=True)
 except Exception as e:out[name]={'asset':asset,'error':str(e)};print(name,str(e)[:100],flush=True)
 (OUT/'source_inventories.json').write_text(json.dumps(out,indent=2)+'\n')
