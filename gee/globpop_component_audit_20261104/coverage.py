"""Read-only native frames enclosing actual GlobPOP missing footprints."""
import ee,json,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_component_audit_20261104';ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
gaps=json.loads((ROOT/'data/pantanal_covariates/globpop_production_review_20261104/finite_gap_pixels.json').read_text());summary={}
for source in ['landscan','ghs_2023','ghs_2016']:
 for key in gaps:
  group,year=key.split('_');year=int(year);ps=gaps[key]
  # Historical GHSL2016 has only2000/2015 in our vicinity; current2023 is five-year.
  if source=='landscan':epoch=year;asset=f'projects/sat-io/open-datasets/ORNL/LANDSCAN_GLOBAL/landscan-global-{epoch}';band='b1'
  else:
   epoch=2015 if source=='ghs_2016' else min([2005,2010,2015],key=lambda y:(abs(y-year),y));asset=f'JRC/GHSL/{"P2023A/GHS_POP"if source=="ghs_2023"else"P2016/POP_GPW_GLOBE_V1"}/{epoch}';band='population_count'
  runkey=f'{source}_{group}_{year}_epoch{epoch}';im=ee.Image(asset).select(band);meta=im.getInfo();west=min(-180+p['source_col']/120 for p in ps);east=max(-180+(p['source_col']+1)/120 for p in ps);north=max(90-p['source_row']/120 for p in ps);south=min(90-(p['source_row']+1)/120 for p in ps);region=ee.Geometry.Rectangle([west,south,east,north],'EPSG:4326',False)
  raw=im.rename('count').addBands(im.mask().rename('validmask')).toDouble().sampleRectangle(region,defaultValue=-9999).getInfo()['properties'];a=np.array(raw['count'],float);m=np.array(raw['validmask'],float);np.savez_compressed(OUT/(runkey+'.npz'),count=a,mask=m)
  valid=np.isfinite(a)&(m>0)&(a>=0);summary[runkey]={'asset':asset,'target_year':year,'selected_epoch':epoch,'source_projection':meta['bands'][0],'source_properties':meta['properties'],'native_frame_lonlat':[west,south,east,north],'native_frame_shape':list(a.shape),'native_frame_pixels':int(a.size),'finite_nonnegative_maskvalid_pixels':int(valid.sum()),'nonfinite_pixels':int((~np.isfinite(a)).sum()),'masked_pixels':int((m<=0).sum()),'negative_or_sentinel_pixels':int((a<0).sum()),'zero_valid_pixels':int((valid&(a==0)).sum()),'maximum_native_count':float(a[valid].max())if valid.any()else None,'minimum_native_count':float(a[valid].min())if valid.any()else None,'scope':'Native bounding frame enclosing ALL missing footprints, includes intervening cells; not an aggregation or density product.'}
  (OUT/'coverage_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(runkey,a.shape,int(valid.sum()),'/',a.size,flush=True)
