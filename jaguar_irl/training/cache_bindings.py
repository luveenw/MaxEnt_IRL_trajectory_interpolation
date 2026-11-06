"""Resolve split-specific year plans to shared cached arrays and feature bindings.

The selector does not copy/cache/modify rasters. Scaling is an explicit choice;
training-only fitted parameters can be reused unchanged by the test binding.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import os
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import file_hash
from .shared_storage import read,write,locked

ROOT=Path(__file__).resolve().parents[2]
FEATURES=['roughness','human_population','grassland','tree_cover','flooded_habitat','shrubland']
DEFINITIONS={
 'roughness':'SRTM elevation population variance in 90m (3x3) windows on30m metric grid, overlap mean in500m cell; static source.',
 'human_population':'Annual published GlobPOP density surface physical-overlap mean; actual same-year LandScan zero fallback only at approved native gaps, corroborated by GHSL; not a conserved resident census.',
 'grassland':'MapBiomas natural grassland class12 fraction; managed pasture excluded; Bolivia grass/shrub mixture accepted.',
 'tree_cover':'MapBiomas classes3+4 forest/savanna classified-area fraction, excluding6/7; includes tree/shrub mixtures, not measured canopy closure.',
 'flooded_habitat':'MapBiomas class11 narrow herbaceous/shrubby flooded habitat fraction; excludes open water and flooded woody classes6/7.',
 'shrubland':'Annual ESA CCI classes120/121/122 shrubland classified-area fraction.'}


def checked_feature(inventory,group,year,name):
    pair=f'{group}_{year}'
    if pair not in inventory['group_years']:raise ValueError(f'Missing candidate cache {pair}')
    item=inventory['group_years'][pair];entry=item['features'][name];path=Path(entry['path'])
    path=(path if path.is_absolute() else ROOT/path).resolve()
    if file_hash(path)!=entry['sha256']:raise ValueError(f'Cache changed: {path}')
    validation=Path(entry['validation_path']);validation=validation if validation.is_absolute() else ROOT/validation
    if file_hash(validation)!=entry['validation_sha256']:raise ValueError('Cached validation changed')
    v=read(validation)
    if v['grid']['grid_key']!=item['grid_key']:raise ValueError('Cache validation grid mismatch')
    a=np.load(path,mmap_mode='r',allow_pickle=False)
    if a.shape!=tuple(item['shape']) or not np.isfinite(a).all():raise ValueError('Bad feature shape/values')
    return path,entry,v


def save_frozen(path,value):
    path=Path(path).resolve()
    with locked(path.parent):
        if path.exists():
            if read(path)!=value:raise ValueError(f'Existing output differs: {path}; use a new version')
        else:
            tmp=path.with_suffix('.pending');write(tmp,value);tmp.replace(path)
    return path


def fit_scaling(plan_path,inventory_path,output):
    plan=read(plan_path);inventory=read(inventory_path)
    if plan['split']!='train':raise ValueError('Scaling must be fitted from a train plan')
    # Stable per-animal moments, combining all departure states including inferred
    # connectors. Every animal has equal total mass; within animal each state
    # visit has equal mass, including repeated visits. This does not change J.
    moments={};arrays={}
    for r in plan['trajectories']:
        g=r['group_id'];year=plan['groups'][g]['representative_season_year']
        if g not in arrays:
            arrays[g]=[np.load(checked_feature(inventory,g,year,n)[0],mmap_mode='r',allow_pickle=False) for n in FEATURES]
        if file_hash(r['path'])!=r['sha256']:raise ValueError('Training trajectory changed')
        route=np.load(r['path'],allow_pickle=False)
        if route.ndim!=2 or route.shape[1]!=3 or len(route)<3:raise ValueError('Invalid departure-state trajectory')
        x=np.stack([a[route[:-1,0],route[:-1,1]] for a in arrays[g]]).astype(float)
        n=x.shape[1];mean=x.mean(axis=1);m2=((x-mean[:,None])**2).sum(axis=1)
        animal=r['individual_id']
        if animal in moments:
            old,mu,m= moments[animal];total=old+n;delta=mean-mu
            moments[animal]=(total,mu+delta*n/total,m+m2+delta**2*old*n/total)
        else:moments[animal]=(n,mean,m2)
    if not moments:raise ValueError('No training observations for scaling')
    mean=np.mean([m[1] for m in moments.values()],axis=0)
    variance=np.mean([m2/n+(mu-mean)**2 for n,mu,m2 in moments.values()],axis=0);sd=np.sqrt(variance)
    params={name:dict(offset=float(mean[i]),scale=float(sd[i]) if sd[i]>0 else 1.,
        training_standard_deviation=float(sd[i]),constant_in_training=bool(sd[i]==0)) for i,name in enumerate(FEATURES)}
    result=dict(schema='shared_covariate_scaling/1',policy='equal_animal_route_departure_zscore',fit_split='train',
        weighting='Equal total mass per animal; equal departure-state visits within each animal, across all routes/years; inferred connectors included; terminal states excluded',
        units='Raw units retained in bindings; scaled features are standardized values',
        source_plan_sha256=file_hash(plan_path),inventory_sha256=file_hash(inventory_path),
        animal_ids=sorted(moments,key=int),departure_counts={i:m[0] for i,m in moments.items()},
        features=params,software_sha256=file_hash(__file__))
    return save_frozen(output,result)


def fit_bounds(plan_path,inventory_path,output):
    """Freeze increasing [-1,0] affine scales from full selected training maps."""
    plan=read(plan_path);inventory=read(inventory_path)
    if plan['split']!='train':raise ValueError('Bounds must be fitted from a train plan')
    maps={};upper={n:0. for n in FEATURES[:2]}
    for group,choice in sorted(plan['groups'].items()):
        year=choice['representative_season_year'];records={}
        for name in FEATURES:
            path,entry,_=checked_feature(inventory,group,year,name)
            a=np.load(path,mmap_mode='r',allow_pickle=False)
            low,high=float(a.min()),float(a.max())
            if low<0 or (name not in upper and high>1):raise ValueError('Feature outside physical bounds')
            if name in upper:upper[name]=max(upper[name],high)
            records[name]=dict(path=str(path),sha256=entry['sha256'],minimum=low,maximum=high,cell_count=int(a.size))
        maps[group]=dict(year=year,features=records)
    if not maps or any(v<=0 for v in upper.values()):raise ValueError('Need positive training upper bounds')
    params={n:dict(offset=upper.get(n,1.),scale=upper.get(n,1.)) for n in FEATURES}
    result=dict(schema='shared_covariate_scaling/1',policy='hirakawa_style_training_map_upper_bounds',
        fit_split='train',source_plan_sha256=file_hash(plan_path),inventory_sha256=file_hash(inventory_path),
        features=params,maps=maps,software_sha256=file_hash(__file__),
        rule='(x-U)/U; full selected training maps including padding, shared across maps; fraction U=1; no clipping or test refitting')
    return save_frozen(output,result)


def resolve(plan_path,inventory_path,output,secondary_plan=None,scaling_file=None,identity=False):
    if bool(scaling_file)==bool(identity):raise ValueError('Choose explicit identity scaling or a fitted scaling file')
    plan=read(plan_path);inventory=read(inventory_path)
    other=read(secondary_plan) if secondary_plan else None
    if other and (other['checkpoint_sha256']!=plan['checkpoint_sha256'] or other['export_sha256']!=plan['export_sha256']):raise ValueError('Context plans do not share checkpoint/export')
    if scaling_file:
        scaling=read(scaling_file)
        if scaling['fit_split']!='train' or scaling['inventory_sha256']!=file_hash(inventory_path):raise ValueError('Invalid training scaling provenance')
        train=plan if plan['split']=='train' else other
        if train is None or train['split']!='train' or scaling['source_plan_sha256']!=file_hash(plan_path if plan['split']=='train' else secondary_plan):raise ValueError('Scaling does not match this training plan')
        params=scaling['features']
    else:params={n:dict(offset=0.,scale=1.)for n in FEATURES}
    groups={};target=Path(output).resolve()
    # Include the whole requested inventory to satisfy the existing prep contract.
    # Opposite-context-only maps are explicitly inactive for this primary role.
    # Such maps contribute no fitting likelihood and do not choose active epochs.
    for g in plan['requested_groups']:
        owner=plan if g in plan['groups'] else other
        if owner is None or g not in owner['groups']:raise ValueError(f'No context supplies map {g}')
        choice=owner['groups'][g];year=choice['representative_season_year'];pair=f'{g}_{year}'
        item=inventory['group_years'].get(pair)
        if item is None or item['grid_key']!=choice['grid_key']:raise ValueError('Year-plan/cache grid mismatch')
        files={}
        for name in FEATURES:
            path,entry,v=checked_feature(inventory,g,year,name)
            files[name]=dict(path=os.path.relpath(path,target.parent),cache_group_year=pair,
                source_epoch=2000 if name=='roughness' else year,source_context_split=owner['split'],
                active_for_primary_split=g in plan['groups'],product_key=v['product_key'],
                validation_path=entry['validation_path'],validation_sha256=entry['validation_sha256'])
        groups[g]=dict(grid_key=choice['grid_key'],season=plan['season'],temporal_scope=plan['temporal_scope'],files=files)
    sample=next(iter(inventory['group_years'].values()))['features']
    features=[dict(name=n,units=sample[n]['units'],definition=DEFINITIONS[n],offset=params[n]['offset'],scale=params[n]['scale']) for n in FEATURES]
    spec=dict(biome='Pantanal',features=features,groups=groups,
        provenance=dict(schema='cache_resolved_binding_manifest/1',primary_split=plan['split'],
        primary_plan=str(Path(plan_path).resolve()),primary_plan_sha256=file_hash(plan_path),
        secondary_plan_sha256=file_hash(secondary_plan) if secondary_plan else None,
        inventory_sha256=file_hash(inventory_path),scaling_policy='identity_raw_units' if identity else scaling['policy'],
        scaling_sha256=file_hash(scaling_file) if scaling_file else None,
        inactive_inventory_maps=plan['groups_without_split_evidence'],software_sha256=file_hash(__file__),
        note='Shared files, not split-owned copies. Secondary-context maps are inventory-only for the primary role.'))
    return save_frozen(output,spec)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    fit=sub.add_parser('fit-scaling');fit.add_argument('--plan',dest='plan_path',required=True);fit.add_argument('--inventory',dest='inventory_path',required=True);fit.add_argument('--output',required=True)
    bounds=sub.add_parser('fit-bounds');bounds.add_argument('--plan',dest='plan_path',required=True);bounds.add_argument('--inventory',dest='inventory_path',required=True);bounds.add_argument('--output',required=True)
    q=sub.add_parser('resolve');q.add_argument('--plan',dest='plan_path',required=True);q.add_argument('--inventory',dest='inventory_path',required=True);q.add_argument('--output',required=True);q.add_argument('--secondary-plan');q.add_argument('--scaling-file');q.add_argument('--identity',action='store_true')
    a=vars(p.parse_args());command=a.pop('command');print({'fit-scaling':fit_scaling,'fit-bounds':fit_bounds,'resolve':resolve}[command](**a))

if __name__=='__main__':main()
