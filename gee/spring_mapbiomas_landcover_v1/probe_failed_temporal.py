"""Read-only temporal/source mask diagnosis of rejected native G316 pixel."""
from pathlib import Path
import ee,json
from jaguar_irl.training.mapbiomas_landcover import SOURCES
from jaguar_irl.training.shared_storage import write,read
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
ee.Initialize(project='perceptive-ivy-780')
pt=ee.Geometry.Point([-57.58843266634279,-17.83771184946872])
result={}
for country,asset in SOURCES.items():
    img=ee.Image(asset);fields={}
    for year in (2005,2010,2011,2012,2015):
        src=img.select(f'classification_{year}');proj=src.projection()
        fields[str(year)]=ee.Dictionary({'projection':proj,'values':src.unmask(-9999,False).rename('class').addBands(src.mask().unmask(0,False).rename('mask')).reduceRegion(ee.Reducer.first(),pt,crs=proj,maxPixels=10)})
    result[country]=ee.Dictionary(fields)
result=ee.Dictionary(result).getInfo();write(DATA/'failed_G316_temporal_diagnosis.json',result);print(json.dumps(result,indent=2))
