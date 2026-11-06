"""Read-only audit of classes actually selected by the requested country priority."""
import ee,json
from pathlib import Path
root=Path(__file__).resolve().parents[3];out=Path(__file__).resolve().parent
ee.Initialize(project='perceptive-ivy-780')
meta=json.loads((root/'data/pantanal_covariates/mapbiomas_access_audit_20261103/asset_metadata.json').read_text());plan=json.loads((root/'data/pantanal_covariates/spring_srtm_roughness_v1/jobs/plan.json').read_text());years=[2005,2006,2008,2009,2010,2011,2012,2013,2014,2015]
region=ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)) for j in plan['groups'].values()]).geometry()
imgs={}
for c in ('brazil','paraguay','bolivia'):
 z=ee.Image(meta[c]['id']).select(['classification_'+str(y) for y in years]);imgs[c]=z.updateMask(z.neq(0).And(z.neq(27)))
covered=None;report={'country_priority':['brazil','paraguay','bolivia'],'years':years,'chosen_classes':{}}
for c,z in imgs.items():
 m=z.mask().gt(0)
 chosen=z if covered is None else z.updateMask(covered.Not())
 hist=chosen.reduceRegion(ee.Reducer.frequencyHistogram(),region,crs=z.select(0).projection(),maxPixels=100000000,tileScale=4).getInfo()
 report['chosen_classes'][c]={'codes':sorted({int(k) for b in hist.values() if b for k in b}),'histograms':hist}
 covered=m.unmask(0,False) if covered is None else covered.Or(m.unmask(0,False))
 print(c,report['chosen_classes'][c]['codes'],flush=True)
 (out/'priority_selected_classes.json').write_text(json.dumps(report,indent=2)+'\n')
