"""Read-only temporal and regional-source checks of diagnosed native gaps."""
from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/mapbiomas_gap_diagnosis_20261103'
SCRIPT_ROOT = REPO/'gee/mapbiomas_gap_diagnosis_20261103'
import ee,json
from pathlib import Path
ROOT=REPO;OUT=DATA_ROOT
d=json.loads((OUT/'diagnosis.json').read_text());ee.Initialize(project='perceptive-ivy-780')
imgs={k:ee.Image(v) for k,v in d['assets'].items()};proj=imgs['brazil'].select(0).projection()
p=json.loads((ROOT/'gee/spring_srtm_roughness_v1/jobs/plan.json').read_text());j=p['groups']['G115'];g=j['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False);target=ee.Projection(g['crs'],j['crs_transform'])
def union(xs):return ee.ImageCollection([x.rename('u') for x in xs]).max().setDefaultProjection(proj)
mask=union([z.select('classification_2005').mask().gt(0).unmask(0,False) for z in imgs.values()]);bad=mask.eq(0)
chaco=ee.Image('projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2')
result={'chaco_asset':chaco.get('system:id').getInfo(),'chaco_bands':chaco.bandNames().getInfo()}
gap_points=[f['geometry']['coordinates'] for f in json.loads((ROOT/'data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_gap_probe.json').read_text())['incomplete_cells']['features']]
gap_region=ee.Geometry.Rectangle([min(p[0] for p in gap_points)-.005,min(p[1] for p in gap_points)-.005,max(p[0] for p in gap_points)+.005,max(p[1] for p in gap_points)+.005],'EPSG:4326',False).intersection(region,ee.ErrorMargin(1))
result['chaco_gap_histograms']=chaco.updateMask(bad).reduceRegion(ee.Reducer.frequencyHistogram(),gap_region,crs=d['native_projections']['brazil']['crs'],crsTransform=d['native_projections']['brazil']['transform'],maxPixels=5000000).getInfo()
result['national_any_year_valid_at_gaps']={k:z.mask().gt(0).unmask(0,False).reduce(ee.Reducer.max()).updateMask(bad).reduceRegion(ee.Reducer.max(),gap_region,crs=d['native_projections']['brazil']['crs'],crsTransform=d['native_projections']['brazil']['transform'],maxPixels=5000000).getInfo() for k,z in imgs.items()}
cv=chaco.mask().gt(0).And(chaco.neq(0)).And(chaco.neq(27)).reduce(ee.Reducer.min()).unmask(0,False)
combined=mask.max(cv).setDefaultProjection(proj)
coarse=combined.reduceResolution(ee.Reducer.mean(),maxPixels=1024).reproject(target)
result['national_2005_plus_chaco_all_years_full_grid']=coarse.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True),region,crs=g['crs'],crsTransform=j['crs_transform'],maxPixels=10000).getInfo()
prior=json.loads((ROOT/'data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_gap_probe.json').read_text())
result['missing_projected_area_m2']=sum(1-f['properties']['coverage'] for f in prior['incomplete_cells']['features'])*500*500
(OUT/'fill_checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
