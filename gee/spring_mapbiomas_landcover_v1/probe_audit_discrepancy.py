"""Explain why a prior across-year mask audit missed a transient source hole."""
from pathlib import Path
import ee,json
from jaguar_irl.training.mapbiomas_landcover import SOURCES
from jaguar_irl.training.shared_storage import write
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
ee.Initialize(project='perceptive-ivy-780')
pt=ee.Geometry.Point([-57.58843266634279,-17.83771184946872])
years=[2005,2006,2008,2009,2010,2011,2012,2013,2014,2015]
src=ee.Image(SOURCES['brazil']).select(['classification_'+str(y) for y in years]);base=src.select(0).projection()
per_year=src.mask().gt(0).And(src.neq(0)).And(src.neq(27))
old=per_year.reduce(ee.Reducer.min()).unmask(0,False).rename('old_min_after_masked_bands')
strict=per_year.unmask(0,False).reduce(ee.Reducer.min()).rename('strict_min_after_per_band_unmask')
result=old.addBands(strict).reduceRegion(ee.Reducer.first(),pt,crs=base,maxPixels=10).getInfo()
result.update(explanation='Across-band reducers skip masked yearly values. The earlier audit unmasked only after reduction, so a transient annual hole could be hidden by valid other years. Strict across-year validation must unmask invalid values before reducing.',source=SOURCES['brazil'],year_with_hole=2011)
write(DATA/'earlier_audit_discrepancy.json',result);print(json.dumps(result,indent=2))
