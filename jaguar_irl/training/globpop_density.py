"""Physical overlap aggregation of published GlobPOP density with guarded LandScan fallback.

Native angular pixels are curved in UTM. Edges are densified before planar
intersection; intersection areas are measured on the WGS84 ellipsoid. This is a
mean of the published density surface, not a census/population conservation claim.
"""
from pathlib import Path
import math
import numpy as np
from pyproj import Transformer, Geod
from shapely.geometry import Polygon, box

DENSITY='projects/sat-io/open-datasets/GLOBPOP_DENSITY'
LANDSCAN='projects/sat-io/open-datasets/ORNL/LANDSCAN_GLOBAL'
BANDS=['human_population_density','globpop_observed_fraction','landscan_fallback_fraction','effective_valid_fraction']
RECIPE=dict(id='globpop_density_landscan_guarded_zero_physical_overlap_v1',feature=BANDS[0],units='people/km2',
 meaning='Physical overlap-area weighted mean of published GlobPOP density surface; ambient LandScan source fallback only at audited missing pixels',
 native_resolution='30 arc-seconds',target='exact saved500m EPSG32721 cells including5km padding',
 aggregation='native angular polygons densified64segments/edge, UTM intersection, WGS84 ellipsoidal physical overlap areas',
 smoothing=None,temporal='annual calendar-year estimate applied throughout Spring Aug15-Nov14; no sub-season observation',
 fallback='Only approved exact native pixels and actual missing/nonfinite GlobPOP; same-year observed finite LandScan count must equal0; zero/full native physical area=0',
 nodata=-9999,export_bands=BANDS,interpretation='No claim of GlobPOP full-cell versus land-only denominator equivalence, population conservation, true human absence or local census accuracy')
GEOD=Geod(ellps='WGS84')


def angular_polygon(col,row,transform,project,segments=64):
    a,b,c,d,e,f=transform
    if b or d:raise ValueError('Rotated native grid unsupported')
    x0=c+a*col;x1=x0+a;y1=f+e*row;y0=y1+e;pts=[]
    for start,end in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
        t=np.arange(segments)/segments
        xs=start[0]+t*(end[0]-start[0]);ys=start[1]+t*(end[1]-start[1]);px,py=project.transform(xs,ys);pts.extend(zip(px,py))
    return Polygon(pts)


def physical_area(poly,inverse):
    if poly.is_empty:return 0.0
    if poly.geom_type=='MultiPolygon':return sum(physical_area(p,inverse)for p in poly.geoms)
    x,y=poly.exterior.xy;lon,lat=inverse.transform(x,y);area=abs(GEOD.polygon_area_perimeter(lon,lat)[0])
    for ring in poly.interiors:
        x,y=ring.xy;lon,lat=inverse.transform(x,y);area-=abs(GEOD.polygon_area_perimeter(lon,lat)[0])
    return area


def build_overlaps(grid,transform,xs,ys):
    """Sparse local/native index and physical-area mapping; no data values needed."""
    project=Transformer.from_crs(4326,grid['crs'],always_xy=True);inverse=Transformer.from_crs(grid['crs'],4326,always_xy=True)
    xmin,ymin,xmax,ymax=grid['bounds'];cell=grid['cell_size_m'];domain=box(xmin,ymin,xmax,ymax)
    target=[];native=[];areas=[];projected=[]
    for nr,nc in np.ndindex(xs.shape):
        polygon=angular_polygon(int(xs[nr,nc]),int(ys[nr,nc]),transform,project).intersection(domain)
        if polygon.is_empty or polygon.area<1e-7:continue
        left,bottom,right,top=polygon.bounds
        rmin=max(0,math.floor((ymax-top)/cell));rmax=min(grid['rows']-1,math.floor((ymax-bottom)/cell))
        cmin=max(0,math.floor((left-xmin)/cell));cmax=min(grid['cols']-1,math.floor((right-xmin)/cell))
        for row in range(rmin,rmax+1):
            for col in range(cmin,cmax+1):
                piece=polygon.intersection(box(xmin+col*cell,ymax-(row+1)*cell,xmin+(col+1)*cell,ymax-row*cell))
                if piece.is_empty or piece.area<1e-7:continue
                target.append(row*grid['cols']+col);native.append(nr*xs.shape[1]+nc);areas.append(physical_area(piece,inverse));projected.append(piece.area)
    size=grid['rows']*grid['cols'];target=np.array(target,np.int64);native=np.array(native,np.int64);areas=np.array(areas)
    sums=np.bincount(target,weights=areas,minlength=size)
    # Independent physical cell areas with densified UTM boundaries.
    expected=[]
    for row in range(grid['rows']):
        for col in range(grid['cols']):
            x=xmin+col*cell;y=ymax-row*cell;pts=[]
            for p,q in [((x,y-cell),(x+cell,y-cell)),((x+cell,y-cell),(x+cell,y)),((x+cell,y),(x,y)),((x,y),(x,y-cell))]:
                for t in np.arange(8)/8:pts.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
            expected.append(physical_area(Polygon(pts),inverse))
    expected=np.array(expected)
    if not np.allclose(sums,expected,rtol=2e-7,atol=.02):raise ValueError('Native polygons do not completely partition target cells')
    return dict(target=target,native=native,area=areas,projected_area=np.array(projected),target_area=expected,
                area_sum=sums,shape=np.array([grid['rows'],grid['cols']]))


def aggregate(raw,overlaps,approved):
    d=raw['density'].astype(float).ravel();mask=raw['density_mask'].ravel()>0
    xs=raw['x'].ravel();ys=raw['y'].ravel();active=np.unique(overlaps['native'])
    if np.any(np.isfinite(d[active]) & mask[active] & (d[active]<0)):
        raise ValueError('Finite negative observed density is invalid, not a missing-value fallback')
    valid=np.isfinite(d)&mask&(d>=0);fallback=np.zeros(d.shape,bool)
    bad=active[~valid[active]];actual={(int(xs[i]),int(ys[i]))for i in bad}
    allowed={tuple(p)for p in approved}
    if actual!=allowed:raise ValueError(f'Current missing footprint differs from approved scope: {actual ^ allowed}')
    ls=raw['landscan_count'].ravel();lm=raw['landscan_mask'].ravel()>0
    for i in bad:
        if not lm[i] or not np.isfinite(ls[i]) or ls[i]!=0:raise ValueError('Fallback requires observed finite same-year LandScan count0')
        d[i]=0;fallback[i]=True
    # Native finite values are untouched. Invalid unneeded bbox corners are excluded.
    n=overlaps['native'];t=overlaps['target'];a=overlaps['area'];den=overlaps['area_sum'];size=len(den)
    if not np.isfinite(d[n]).all() or np.any(d[n]<0):raise ValueError('Incomplete effective native coverage')
    mean=np.bincount(t,weights=a*d[n],minlength=size)/den
    frac=np.bincount(t,weights=a*fallback[n],minlength=size)/den
    observed=np.bincount(t,weights=a*valid[n],minlength=size)/den
    coverage=observed+frac
    if not np.allclose(coverage,1,rtol=0,atol=1e-9):raise ValueError('Source coverage incomplete')
    data=np.stack([mean,observed,frac,coverage]).reshape((4,*overlaps['shape']))
    if not np.isfinite(data).all():raise ValueError('Nonfinite aggregate')
    return data,dict(native_fallback_pixels=len(bad),fallback_cells=int(np.count_nonzero(frac>1e-9)),
       fallback_physical_area_m2=float(np.dot(frac,overlaps['area_sum'])),
       fallback_projected_area_m2=float(np.sum(overlaps['projected_area'][fallback[n]])),
       minimum=float(mean.min()),maximum=float(mean.max()),mean=float(mean.mean()),
       observed_native_values_preserved=True,maximum_coverage_error=float(np.abs(coverage-1).max()))
