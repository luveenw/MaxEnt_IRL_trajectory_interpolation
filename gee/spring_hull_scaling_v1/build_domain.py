"""Build/check a hull from finalized padded extents; never overwrite a new domain.

Run only after all seasonal extent/covariate extractions have been completed.
"""
import argparse
import json
from pathlib import Path
from shapely.geometry import box,mapping
from shapely.ops import unary_union

def build(plan_path,output,season='Spring'):
    plan=json.loads(Path(plan_path).read_text());groups=plan['groups']
    if not groups:raise ValueError('No finalized extents')
    grids=[v['grid'] for v in groups.values()]
    if len({g['crs'] for g in grids})!=1 or len({g['cell_size_m']for g in grids})!=1:
        raise ValueError('Resolve common CRS/lattice before building reference')
    cell=grids[0]['cell_size_m'];transform=[cell,0,0,0,-cell,10000000]
    if any(any(abs(v/cell-round(v/cell))>1e-8 for v in g['bounds'])for g in grids):
        raise ValueError('Extents do not align to this reference lattice')
    union=unary_union([box(*g['bounds'])for g in grids]);hull=union.convex_hull
    if not hull.is_valid or not all(hull.covers(box(*g['bounds']))for g in grids):raise ValueError('Invalid hull')
    result=dict(crs=grids[0]['crs'],geometry=mapping(hull),group_ids=sorted(groups),area_km2=hull.area/1e6,
        union_area_km2=union.area/1e6,grid_transform=transform,
        scope=f'Convex hull of all {len(groups)} padded selected {season} map rectangles')
    result=json.loads(json.dumps(result));output=Path(output)
    if output.exists():
        if json.loads(output.read_text())!=result:raise ValueError('Existing domain differs; use a new versioned output')
        print('Existing hull reproduced exactly:',output)
    else:
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print('Saved:',output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--extent-plan',required=True);p.add_argument('--output',required=True);p.add_argument('--season',default='Spring')
    args=p.parse_args();build(args.extent_plan,args.output,args.season)
