"""Bounded read-only GlobPOP native count/density diagnostics."""
import json,hashlib
from pathlib import Path
import ee,numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
pilots=json.loads((ROOT/'data/pantanal_covariates/globpop_access_20261104/pilots.json').read_text())
results={}
for key,p in pilots.items():
 year=p['year'];g=p['grid'];r=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
 ims={k:ee.ImageCollection('projects/sat-io/open-datasets/GLOBPOP_'+k.upper()).filterDate(f'{year}-01-01',f'{year+1}-01-01').first().select('b1').rename(k) for k in ['density','count']}
 image=ims['density'].addBands(ims['count']).addBands(ims['density'].mask().rename('density_mask')).addBands(ims['count'].mask().rename('count_mask'))
 rect=image.toDouble().sampleRectangle(r,defaultValue=-9999).getInfo();(OUT/(key+'_raw_rectangle.json')).write_text(json.dumps(rect,indent=2));props=rect['properties'];d=np.array(props['density'],dtype=float);c=np.array(props['count'],dtype=float);dm=np.array(props['density_mask'],dtype=float);cm=np.array(props['count_mask'],dtype=float)
 np.savez_compressed(OUT/(key+'_native.npz'),density=d,count=c,density_mask=dm,count_mask=cm)
 valid=(dm>0)&(cm>0)&(d>0);positive=(valid)&(c>0)
 ratios=c[positive]/d[positive]
 results[key]={'density_image_id':ims['density'].get('system:id').getInfo(),'count_image_id':ims['count'].get('system:id').getInfo(),'geometry':rect['geometry'],'shape':list(d.shape),'native_pixels':int(d.size),'density_mask_valid':int((dm>0).sum()),'count_mask_valid':int((cm>0).sum()),'density_positive_count_zero_valid':int((valid&(c==0)).sum()),'density_positive_count_masked':int(((dm>0)&(d>0)&(cm<=0)).sum()),'count_to_density_ratio_km2_min':float(ratios.min()) if len(ratios) else None,'count_to_density_ratio_km2_max':float(ratios.max()) if len(ratios) else None,'count_integer_values':bool(np.all(c[cm>0]==np.round(c[cm>0]))),'native_data_file':key+'_native.npz'}
 (OUT/'native_diagnostics.json').write_text(json.dumps(results,indent=2)+'\n');print(key,results[key],flush=True)
(OUT/'probe_provenance.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'project':'perceptive-ivy-780','status':'read-only; no exports'},indent=2)+'\n')
