import ee,json
from pathlib import Path
ee.Initialize(project='perceptive-ivy-780')
ids={
'brazil':'projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3',
'bolivia':'projects/mapbiomas-public/assets/bolivia/lulc/collection4/mapbiomas_bolivia_collection4_coverage_v1',
'paraguay':'projects/mapbiomas-public/assets/paraguay/lulc/collection3/mapbiomas_paraguay_collection3_coverage_v1',
'paraguay_old':'projects/mapbiomas-public/assets/paraguay/collection2/mapbiomas_paraguay_collection2_integration_v1',
'brazil_catalog':'projects/mapbiomas-public/assets/brazil/lulc/v1'}
out={}
for k,v in ids.items():
 try:
  a=ee.data.getAsset(v); out[k]=a
  print(k,json.dumps({'name':a.get('name'),'type':a.get('type'),'bands':[b['id'] for b in a.get('bands',[])],'properties':a.get('properties')}),flush=True)
 except Exception as e:
  out[k]={'error':str(e)};print(k,str(e),flush=True)
(Path(__file__).resolve().parent/'asset_metadata.json').write_text(json.dumps(out,indent=2))
