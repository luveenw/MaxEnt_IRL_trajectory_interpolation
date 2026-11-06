"""Index all six completed Spring caches without assigning products to splits.

This read-only array/product check writes a new inventory only after all24pairs
are complete. Source-specific verifiers provide deeper source/Drive/repair QA.
It is an asset index, not a training binding or ecological validation.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import load_selection_checkpoint
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/pantanal_covariates'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(output):
    previous=DATA/'spring_landcover_inventory_v1.json';land=json.loads(previous.read_text())
    wooded_path=DATA/'spring_mapbiomas_wooded_cover_v1/verification.json';wood=json.loads(wooded_path.read_text())
    pop_path=DATA/'spring_globpop_density_v1/verification.json'
    if not pop_path.exists():raise ValueError('Population verification is not complete')
    pop=json.loads(pop_path.read_text())
    cpdir=ROOT/'analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0'
    cp=load_selection_checkpoint(cpdir);groups={g['group_id']:g for g in cp['groups'].values()}
    mapping={'grassland':'grassland_fraction','flooded_habitat':'flooded_habitat_fraction','shrubland':'shrubland_fraction'}
    units={'roughness':'m2 local elevation variance','grassland':'area fraction0–1','flooded_habitat':'area fraction0–1','shrubland':'area fraction0–1','tree_cover':'forest/savanna classified-area fraction0–1','human_population':'published density-surface mean people/km2, with approved source fallback'}
    pairs={};unique={}
    assert len(land['group_years'])==24 and len(wood['products'])==24
    for pair,item in sorted(land['group_years'].items()):
        group,year=pair.split('_');grid=cp['grids'][groups[group]['grid_key']]
        files={name:ROOT/item['features'][stored]['path'] for name,stored in mapping.items()}
        files['tree_cover']=Path(wood['products'][pair]['array_path'])
        files['roughness']=DATA/'spring_srtm_roughness_v1/products'/group/'roughness.npy'
        files['human_population']=DATA/'spring_globpop_density_v1/products'/group/year/'human_population_density.npy'
        result={}
        for name,path in files.items():
            path=path.resolve();array=np.load(path,allow_pickle=False)
            if array.shape!=(grid['rows'],grid['cols']) or not np.isfinite(array).all() or np.any(array<0):raise ValueError(f'Bad shape/nonfinite/negative {path}')
            if name in ('grassland','flooded_habitat','shrubland','tree_cover') and np.any(array>1):raise ValueError(f'Area fraction exceeds1: {path}')
            checks=json.loads((path.parent/'checksums.json').read_text());digest=sha(path)
            if checks.get(path.name)!=digest:raise ValueError(f'Product checksum mismatch: {path}')
            validation=path.parent/'validation.json';v=json.loads(validation.read_text())
            if v['grid']!=grid:raise ValueError(f'Grid mismatch: {path}')
            relative=str(path.relative_to(ROOT));unique[relative]=digest
            result[name]={'path':relative,'sha256':digest,'validation_path':str(validation.relative_to(ROOT)),'validation_sha256':sha(validation),'units':units[name],'recipe_scope':'static terrain shared across years' if name=='roughness' else 'annual candidate product; not assigned to split'}
        pairs[pair]={'group_id':group,'year':int(year),'grid_key':grid['grid_key'],'shape':[grid['rows'],grid['cols']],'features':result}
    report={'schema':'pantanal_spring_covariate_cache_inventory/1','status':'complete array/product integrity; ecological validation pending','epoch_role':'shared split-independent candidate products; no split assignments or bindings','group_year_count':len(pairs),'group_count':len({p['group_id'] for p in pairs.values()}),'features_per_pair':6,'unique_array_count':len(unique),'feature_references':6*len(pairs),'unique_array_bytes':sum((ROOT/p).stat().st_size for p in unique),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [previous,wooded_path,pop_path,cpdir/'checkpoint.json']},'verifier_sha256':sha(Path(__file__)),'group_years':pairs}
    if len(unique)!=133:raise ValueError(f'Expected133uniquearrays, got{len(unique)}')
    output=output.resolve()
    if output.exists():
        if json.loads(output.read_text())!=report:raise ValueError('Inventory differs; use a new output path')
    else:
        from jaguar_irl.training.shared_storage import write
        write(output,report)
    print(json.dumps({k:report[k] for k in ['status','group_year_count','group_count','unique_array_count','feature_references','unique_array_bytes']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DATA/'spring_covariate_cache_inventory_v1.json')
    verify(p.parse_args().output)
