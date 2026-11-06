"""Query hull-wide scaling statistics, without exporting a hull raster.

Population: finite native maxima provide upper bounds for area-weighted means.
A full 500 m cell inside a maximizing native pixel proves the bound is attained
under the production physical-overlap recipe, without a hull-wide resampling.
"""
from pathlib import Path
import math
import sys
import ee
import numpy as np
from shapely.geometry import shape,box
from pyproj import Transformer
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.terrain_roughness import build_ee_image
from jaguar_irl.training.globpop_density import angular_polygon
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/pantanal_covariates/spring_hull_scaling_v1'

def main():
    ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
    domain=read(OUT/'domain.json');h=shape(domain['geometry'])
    region=ee.Geometry(domain['geometry'],proj=domain['crs'],geodesic=False)
    plan_path=ROOT/'data/pantanal_covariates/bindings/spring_whole_animal_v1/train_year_plan.json'
    plan=read(plan_path);years=sorted({v['representative_season_year']for v in plan['groups'].values()})
    if '--population-only' not in sys.argv and not (OUT/'roughness.json').exists():
        job=dict(grid=dict(crs=domain['crs']),crs_transform=domain['grid_transform'])
        im=build_ee_image(ee,job)
        stats=im.reduceRegion(ee.Reducer.minMax(),region,crs=domain['crs'],crsTransform=domain['grid_transform'],maxPixels=2000000,tileScale=4).getInfo()
        if stats['valid_fraction_min']<1-1e-6:raise ValueError('Incomplete roughness coverage')
        write(OUT/'roughness.json',dict(statistics=stats,domain_sha256=file_hash(OUT/'domain.json'),script_sha256=file_hash(__file__)))
    if '--population-only' not in sys.argv:print('roughness',read(OUT/'roughness.json'),flush=True)
    project=Transformer.from_crs(4326,domain['crs'],always_xy=True)
    results={}
    for year in years:
        dest=OUT/f'population_{year}.json'
        if dest.exists():results[str(year)]=read(dest);continue
        asset=f'projects/sat-io/open-datasets/GLOBPOP_DENSITY/GlobPOP_Density_30arc_{year}_F32'
        im=ee.Image(asset).select('b1');projection=im.projection();proj=projection.getInfo()
        finite=im.gte(0).And(im.lt(1e30));im=im.updateMask(finite)
        maximum=im.reduceRegion(ee.Reducer.max(),region,crs=projection,maxPixels=2000000,tileScale=4).getInfo()['b1']
        candidates=im.updateMask(im.eq(maximum)).addBands(ee.Image.pixelCoordinates(projection)).sample(region=region,projection=projection,geometries=False,tileScale=4).limit(1000).getInfo()['features']
        witness=None
        for candidate in candidates:
            props=candidate['properties'];poly=angular_polygon(int(props['x']),int(props['y']),proj['transform'],project)
            left,bottom,right,top=poly.bounds
            for x in range(math.floor(left/500)*500,math.ceil(right/500)*500,500):
                for y in range(math.floor(bottom/500)*500,math.ceil(top/500)*500,500):
                    cell=box(x,y,x+500,y+500)
                    if poly.covers(cell) and h.covers(cell):
                        witness=dict(native_col=props['x'],native_row=props['y'],cell_bounds=list(cell.bounds));break
                if witness:break
            if witness:break
        result=dict(year=year,asset=asset,native_projection=proj,native_finite_maximum=maximum,
                    attained_500m_maximum=maximum if witness else None,witness=witness,
                    proof='Every complete nonnegative physical-overlap mean is at most native max; witness cell lies wholly inside maximizing observed native pixel and hull',
                    missing_policy='No new gap filling. Only finite observed nonnegative source pixels define native maximum.',
                    domain_sha256=file_hash(OUT/'domain.json'),script_sha256=file_hash(__file__))
        write(dest,result);results[str(year)]=result
        print('population',year,maximum,'attained',bool(witness),flush=True)
    if '--population-only' in sys.argv:return
    maximum=max(r['native_finite_maximum']for r in results.values())
    winners=[r for r in results.values() if r['attained_500m_maximum']==maximum]
    if not winners:raise ValueError('Native upper bound not attained; need exact candidate-cell integration before freezing')
    result=dict(roughness_upper=read(OUT/'roughness.json')['statistics']['roughness_var_m2_max'],population_upper=maximum,
                population_winning_years=[r['year']for r in winners],population_years=years,
                train_plan_sha256=file_hash(plan_path),domain_sha256=file_hash(OUT/'domain.json'),software_sha256=file_hash(__file__),
                policy='Convex hull of all padded selected Spring extents; population selected training years only; model-scale maxima; no hull raster exported')
    write(OUT/'maxima.json',result);print(result,flush=True)
if __name__=='__main__':main()
