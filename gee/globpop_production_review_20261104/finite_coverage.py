"""Read-only native finite-value audit, exact UTM overlap diagnostics; no repair."""
import json,math,time
from pathlib import Path
import ee,numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
plan=json.loads((ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json').read_text());jobs=list(plan['groups'].values());jobs.sort(key=lambda j:(j['group_id']!='G316',j['group_id'],j['year']))
trans=Transformer.from_crs(4326,32721,always_xy=True);inverse=Transformer.from_crs(32721,4326,always_xy=True)
def polygon(c,r):
 x0=-180+c/120;x1=x0+1/120;y1=90-r/120;y0=y1-1/120;pts=[]
 for a,b in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
  for t in np.linspace(0,1,33)[:-1]:pts.append(trans.transform(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
 return Polygon(pts)
summary={};details={}
for job in jobs:
 group=job['group_id'];year=job['year'];key=f'{group}_{year}';g=job['grid'];x0,y0,x1,y1=g['bounds'];nativebounds=inverse.transform_bounds(x0,y0,x1,y1,densify_pts=21);c0=math.floor((nativebounds[0]+180)*120);r0=math.floor((90-nativebounds[3])*120)
 im=ee.ImageCollection('projects/sat-io/open-datasets/GLOBPOP_DENSITY').filterDate(f'{year}-01-01',f'{year+1}-01-01').first().select('b1').toDouble()
 region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
 raw=im.addBands(im.mask().rename('validmask')).toDouble().sampleRectangle(region,defaultValue=-9999).getInfo()['properties'];a=np.array(raw['b1'],float);m=np.array(raw['validmask'],float);np.savez_compressed(OUT/(key+'_density_finite_audit.npz'),density=a,mask=m)
 bad=np.argwhere(~np.isfinite(a)|(m<=0)|(a==-9999));pixels=[];cells={};total=0
 for rr,cc in bad:
  p=polygon(c0+int(cc),r0+int(rr));p=p.intersection(box(x0,y0,x1,y1))
  if p.area<=1e-6:continue
  bx0,by0,bx1,by1=p.bounds;affected=[]
  for tr in range(max(0,int((y1-by1)//500)),min(g['rows']-1,int((y1-by0)//500))+1):
   for tc in range(max(0,int((bx0-x0)//500)),min(g['cols']-1,int((bx1-x0)//500))+1):
    cell=box(x0+tc*500,y1-(tr+1)*500,x0+(tc+1)*500,y1-tr*500);area=p.intersection(cell).area
    if area>1e-6:
     affected.append({'row':tr,'col':tc,'area_m2':area,'fraction':area/250000});cells[(tr,tc)]=cells.get((tr,tc),0)+area
  c=c0+int(cc);r=r0+int(rr);lon=-180+(c+.5)/120;lat=90-(r+.5)/120
  pixels.append({'source_col':c,'source_row':r,'longitude':lon,'latitude':lat,'native_value':'NaN'if not np.isfinite(a[rr,cc])else float(a[rr,cc]),'mask':float(m[rr,cc]),'overlap_domain_m2':p.area,'affected_target_cells':affected});total+=p.area
 summary[key]={'native_array_shape':list(a.shape),'native_array_nonfinite':int((~np.isfinite(a)).sum()),'native_array_masked':int((m<=0).sum()),'bad_pixels_intersecting_domain':len(pixels),'affected_target_cells':len(cells),'missing_projected_area_m2':total,'domain_area_m2':(x1-x0)*(y1-y0),'maximum_missing_cell_fraction':max(cells.values())/250000 if cells else 0}
 if pixels:details[key]=pixels
 (OUT/'finite_coverage_summary.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'finite_gap_pixels.json').write_text(json.dumps(details,indent=2)+'\n');print(key,summary[key],flush=True)
 if key=='G316_2011' and pixels:
  points=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p['longitude'],p['latitude']]),{'source_col':p['source_col'],'source_row':p['source_row']}) for p in pixels]);results={}
  for yr in [2009,2010,2011,2012,2013]:
   image=ee.ImageCollection('projects/sat-io/open-datasets/GLOBPOP_DENSITY').filterDate(f'{yr}-01-01',f'{yr+1}-01-01').first().select('b1')
   results[str(yr)]=image.sampleRegions(collection=points,properties=['source_col','source_row'],projection=image.projection(),geometries=True).getInfo()
  (OUT/'G316_adjacent_year_density.json').write_text(json.dumps(results,indent=2)+'\n');print('adjacent years retained',flush=True)
