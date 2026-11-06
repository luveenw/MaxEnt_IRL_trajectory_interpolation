"""Trace the one rejected G316_2011 target cell back to original source codes."""
from pathlib import Path
import ee
from jaguar_irl.training.mapbiomas_landcover import SOURCES,native_mosaic
from jaguar_irl.training.shared_storage import read,write
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
ee.Initialize(project='perceptive-ivy-780')
j=read(HERE/'jobs/plan.json')['groups']['G316_2011'];g=j['grid'];col,row=13,20
xmin=g['bounds'][0]+col*500;ymax=g['bounds'][3]-row*500
region=ee.Geometry.Rectangle([xmin,ymax-500,xmin+500,ymax],g['crs'],False)
ee.Initialize(project='perceptive-ivy-780');chosen,sid,valid,base=native_mosaic(ee,2011)
out=chosen.addBands(sid).addBands(valid)
for c,a in SOURCES.items():out=out.addBands(ee.Image(a).select('classification_2011').reproject(base).unmask(0,False).rename(c))
result=out.updateMask(valid.Not()).sample(region=region,projection=base,geometries=True).getInfo()
write(DATA/'failed_G316_2011_cell_diagnosis.json',result)
print(result)
