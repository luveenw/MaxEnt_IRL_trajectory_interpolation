"""Freeze hull statistics into new profiles; preserve previous immutable profiles."""
from pathlib import Path
import math
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.cache_bindings import FEATURES,save_frozen,resolve
from jaguar_irl.training.shared import bind
from jaguar_irl.data.pantanal_checkpoint import file_hash
ROOT=Path(__file__).resolve().parents[2]

def main():
    data=ROOT/'data/pantanal_covariates';stats=data/'spring_hull_scaling_v1'
    base=data/'bindings/spring_whole_animal_v1';out=base/'hirakawa_hull_bounds'
    maximum=read(stats/'maxima.json');train=base/'train_year_plan.json';inventory=data/'spring_covariate_cache_inventory_v1.json'
    if maximum['train_plan_sha256']!=file_hash(train) or maximum['domain_sha256']!=file_hash(stats/'domain.json'):raise ValueError('Statistics provenance changed')
    paths=[stats/'domain.json',stats/'maxima.json',stats/'roughness.json']+[stats/f'population_{y}.json'for y in maximum['population_years']]
    boundary=read(stats/'population_boundary_check.json')
    if not boundary['passed'] or boundary['domain_sha256']!=file_hash(stats/'domain.json') or boundary['upper_bound']!=maximum['population_upper']:raise ValueError('Boundary check missing or stale')
    upper=dict(roughness=maximum['roughness_upper'],human_population=maximum['population_upper'])
    if any(not math.isfinite(v)or v<=0 for v in upper.values()):raise ValueError('Invalid maxima')
    scale=dict(schema='shared_covariate_scaling/1',policy='hirakawa_style_spring_hull_maxima_training_years',fit_split='train',
        source_plan_sha256=file_hash(train),inventory_sha256=file_hash(inventory),
        features={n:dict(offset=upper.get(n,1.),scale=upper.get(n,1.))for n in FEATURES},
        domain='Convex hull of all 13 selected padded Spring extents, EPSG32721; 76280 km2',
        population_years=maximum['population_years'],rule='(x-U)/U; fraction U=1; frozen across train/test; no clipping or test refitting',
        provenance={str(p.relative_to(ROOT)):file_hash(p)for p in paths},software_sha256='84265ef87c3ea2541b07f6dd7e669f8880205520cb464549f1b2bea3ebb5b718',
        source_note='Population maximum proven attainable in a complete model cell; no new gap fill or full hull raster cache')
    scale_path=save_frozen(out/'scaling.json',scale);profiles={}
    for role,other in [('train','test'),('test','train')]:
        dest=out/role;dest.mkdir(parents=True,exist_ok=True)
        manifest=resolve(base/f'{role}_year_plan.json',inventory,dest/'manifest.json',secondary_plan=base/f'{other}_year_plan.json',scaling_file=scale_path)
        state=bind(ROOT/'analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0',manifest,binding_dir=dest/'binding')
        profiles[role]=dict(manifest=str(manifest),manifest_sha256=file_hash(manifest),binding_state=str(state),binding_sha256=file_hash(state))
    prep=read(base/'preparation.json');prep['profiles']['hirakawa_hull_bounds']=profiles
    prep.update(selected_scaling='hirakawa_hull_bounds',selected_scaling_path=str(scale_path),selected_scaling_sha256=file_hash(scale_path),selected_regularization=0.,
        status='User-selected Spring convex-hull maxima frozen; population selected training years only; zero L2; no optimizer preparation or fit')
    prep['selected_scaling_boundary_validation']=dict(path=str(stats/'population_boundary_check.json'),sha256=file_hash(stats/'population_boundary_check.json'))
    prep['scaling_freeze_driver_sha256']=file_hash(__file__)
    prep.pop('pending_scaling',None);write(base/'preparation.json',prep)
    print(upper)
if __name__=='__main__':main()
