"""Read-only independent context for the genuine G316_2011 source hole."""
from pathlib import Path
import json,ee
from jaguar_irl.training.shared_storage import write
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
ee.Initialize(project='perceptive-ivy-780');pt=ee.Geometry.Point([-57.58843266634279,-17.83771184946872])
jrc=ee.Image(ee.ImageCollection('JRC/GSW1_4/YearlyHistory').filter(ee.Filter.eq('year',2011)).first()).select('waterClass')
esa=ee.Image('users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022').select('y2011')
values={
 'JRC_GSW_2011':jrc.unmask(-9999,False).reduceRegion(ee.Reducer.first(),pt,crs=jrc.projection(),maxPixels=10),
 'ESA_CCI_2011_coarse_context':esa.unmask(-9999,False).reduceRegion(ee.Reducer.first(),pt,crs=esa.projection(),maxPixels=10)}
result=ee.Dictionary(values).getInfo();result['scope']='Diagnostic context only; neither source is adopted to fill the MapBiomas hole';write(DATA/'failed_G316_independent_context.json',result);print(json.dumps(result,indent=2))
