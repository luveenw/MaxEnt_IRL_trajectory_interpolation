"""Conservative geodesic-area allocation of GHSL counts to GlobPOP gap cells."""
import json,math,hashlib
from pathlib import Path
import numpy as np
from pyproj import Transformer,Geod
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[2];SRC=ROOT/'data/pantanal_covariates/globpop_component_audit_20261104';OUT=ROOT/'data/pantanal_covariates/globpop_ghsl_comparison_20261104';GAPS=ROOT/'data/pantanal_covariates/globpop_production_review_20261104/finite_gap_pixels.json'
meta=json.loads((SRC/'coverage_summary.json').read_text());meta.update(json.loads((OUT/'extra_epoch_metadata.json').read_text()) if (OUT/'extra_epoch_metadata.json').exists() else {});gaps=json.loads(GAPS.read_text());geod=Geod(ellps='WGS84');summary={};results={}
def ring_area(coords,inverse=None):
 if inverse:
  q=[]
  for a,b in zip(coords,coords[1:]):
   segments=max(1,math.ceil(math.hypot(a[0]-b[0],a[1]-b[1])/25))
   for t in np.linspace(0,1,segments+1)[:-1]:q.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
  xy=np.array(q);lon,lat=inverse.transform(xy[:,0],xy[:,1])
 else:lon,lat=np.array(coords).T
 return abs(geod.polygon_area_perimeter(lon,lat)[0])
def area(poly,inv):
 if poly.is_empty:return 0.0
 if poly.geom_type=='MultiPolygon':return sum(area(x,inv)for x in poly.geoms)
 if poly.geom_type!='Polygon':return 0.0
 return ring_area(list(poly.exterior.coords),inv)-sum(ring_area(list(x.coords),inv)for x in poly.interiors)
for name in ['ghs_2023_G057_2013_epoch2015','ghs_2023_G286_2010_epoch2010','ghs_2023_G316_2011_epoch2010','ghs_2016_G057_2013_epoch2015','ghs_2016_G286_2010_epoch2015','ghs_2016_G316_2011_epoch2015', *(['ghs_2023_G057_2013_epoch2010'] if 'ghs_2023_G057_2013_epoch2010' in meta else [])]:
 m=meta[name];group=name.split('_')[2];key=next(k for k in gaps if k.startswith(group+'_'));ps=gaps[key];pr=m['source_projection'];dx,_,x0,_,dy,y0=pr['crs_transform'];forward=Transformer.from_crs(4326,pr['crs'],always_xy=True);inverse=Transformer.from_crs(pr['crs'],4326,always_xy=True);b=forward.transform_bounds(*m['native_frame_lonlat'],densify_pts=21);c0=math.floor((b[0]-x0)/dx);c1=math.ceil((b[2]-x0)/dx);r0=math.floor((y0-b[3])/-dy);r1=math.ceil((y0-b[1])/-dy);source_file=(SRC/(name+'.npz')) if (SRC/(name+'.npz')).exists() else (OUT/(name+'.npz'));native=np.load(source_file);counts=native['count'];mask=native['mask'];assert counts.shape==(r1-r0,c1-c0)
 positive=np.argwhere(counts>0);source=[]
 for rr,cc in positive:
  xx=x0+(c0+cc)*dx;yy=y0+(r0+rr)*dy;p=box(xx,yy+dy,xx+dx,yy);source.append((p,float(counts[rr,cc]),area(p,inverse)))
 rows=[]
 for p in ps:
  west=-180+p['source_col']/120;east=west+1/120;north=90-p['source_row']/120;south=north-1/120;pts=[]
  for a,b in [((west,south),(east,south)),((east,south),(east,north)),((east,north),(west,north)),((west,north),(west,south))]:
   for t in np.linspace(0,1,33)[:-1]:pts.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
  lon,lat=np.array(pts).T;xx,yy=forward.transform(lon,lat);target=Polygon(zip(xx,yy));targetarea=abs(geod.polygon_area_perimeter(lon,lat)[0]);pop=0;contrib=0
  for cell,count,cellarea in source:
   if not cell.intersects(target):continue
   intersection=cell.intersection(target);a=area(intersection,inverse)
   if a>1e-8:pop+=count*a/cellarea;contrib+=1
  rows.append({'source_col':p['source_col'],'source_row':p['source_row'],'ghsl_allocated_people':pop,'full_native_footprint_geodesic_area_km2':targetarea/1e6,'ghsl_density_people_per_km2':pop/(targetarea/1e6),'positive_ghsl_cells_contributing':contrib,'landscan_observed_people':0,'landscan_density_people_per_km2':0})
 values=np.array([r['ghsl_allocated_people']for r in rows]);densities=np.array([r['ghsl_density_people_per_km2']for r in rows]);areas=np.array([r['full_native_footprint_geodesic_area_km2']for r in rows]);summary[name]={'source_asset':m['asset'],'selected_epoch':m['selected_epoch'],'gap_footprints':len(rows),'positive_ghsl_cells_in_enclosing_frame':len(positive),'positive_gap_footprints':int((values>0).sum()),'zero_gap_footprints':int((values==0).sum()),'sum_people_full_gap_footprints':float(values.sum()),'maximum_people_one_gap_footprint':float(values.max()),'density_min':float(densities.min()),'density_max':float(densities.max()),'area_weighted_density':float(values.sum()/areas.sum()),'total_full_native_footprint_area_km2':float(areas.sum()),'source_sha256':hashlib.sha256(source_file.read_bytes()).hexdigest(),'source_window_offset':[int(c0),int(r0)],'source_shape':list(counts.shape)};results[name]=rows
 (OUT/'comparison_summary.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'per_gap_comparison.json').write_text(json.dumps(results,indent=2)+'\n');print(name,summary[name],flush=True)
