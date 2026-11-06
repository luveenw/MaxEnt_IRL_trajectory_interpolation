"""Freeze a reproducible whole-animal random holdout from admitted export evidence."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
from jaguar_irl.data.export_pantanal_irl import validate_export
from jaguar_irl.data.pantanal_checkpoint import load_selection_checkpoint, read_table, file_hash
from .shared import selected_groups, resolve_map_budget_exceptions, route_admission
from .shared_storage import locked, read, write


def draw_roles(eligible_ids, represented_ids, test_count, seed):
    """Uniform selection without group/sex/year/route-count strata or redraws."""
    key=lambda x: (0,int(x)) if x.isdecimal() else (1,x)
    eligible=sorted(set(map(str,eligible_ids)),key=key)
    represented=sorted(set(map(str,represented_ids)),key=key)
    if not set(eligible)<=set(represented):raise ValueError('Eligible animals absent from represented roster')
    if not 0<test_count<len(eligible) or seed<0:raise ValueError('Require positive test count below cohort size and nonnegative seed')
    rng=np.random.Generator(np.random.PCG64(seed))
    testing=set(rng.choice(eligible,size=test_count,replace=False).tolist())
    return {i:('test' if i in testing else 'train' if i in eligible else 'unassigned') for i in represented}


def create_split(checkpoint, export, collection, output, test_count=9, seed=20261104):
    checkpoint,export,output=map(lambda p:Path(p).resolve(),(checkpoint,export,output))
    cp=load_selection_checkpoint(checkpoint);manifest=validate_export(export)
    if manifest['checkpoint_sha256']!=file_hash(checkpoint/'checkpoint.json') or manifest.get('collection_id')!=collection:
        raise ValueError('Export checkpoint/collection mismatch')
    groups=selected_groups(checkpoint,None,collection);exceptions=resolve_map_budget_exceptions(cp,groups)
    rows=[r for r in read_table(export/'data/trajectory_manifest.csv') if r['group_id'] in groups and r['variant']=='two_hour' and r['collection']=='independent']
    represented={r['individual_id'] for r in rows}
    admitted=[r for r in rows if route_admission(r,exceptions) is not None]
    eligible={r['individual_id'] for r in admitted}
    roles=draw_roles(eligible,represented,test_count,seed)
    omitted=sorted(represented-eligible,key=int)
    metadata=dict(schema='whole_animal_random_holdout/1',collection=collection,
        checkpoint=str(checkpoint),checkpoint_sha256=file_hash(checkpoint/'checkpoint.json'),
        source_export=str(export),source_export_sha256=file_hash(export/'export_manifest.json'),
        algorithm='NumPy Generator(PCG64(seed)).choice on numerically sorted original eligible animal IDs; without replacement',
        numpy_version=np.__version__,seed=seed,test_count=test_count,group_constraints=False,
        eligible_ids=sorted(eligible,key=int),represented_ids=sorted(represented,key=int),
        eligible_train_ids=[i for i,v in roles.items() if v=='train'],eligible_test_ids=[i for i,v in roles.items() if v=='test'],
        unassigned_ineligible={i:dict(Counter(r['optimizer_exclusion_reason'] for r in rows if r['individual_id']==i)) for i in omitted},
        split_counts=dict(Counter(roles.values())),admitted_route_count=len(admitted),map_budget_exceptions=exceptions,
        software_sha256=file_hash(__file__),allocation_role='One frozen outer allocation; all years/bursts/variants inherit original animal role; no folds or performance-based redraw')
    with locked(output):
        path=output/'animal_splits.json';meta=output/'split_metadata.json'
        for target,value in [(path,roles),(meta,metadata)]:
            if target.exists():
                if read(target)!=value:raise ValueError('Frozen split differs; do not redraw in place')
            else:
                tmp=target.with_suffix('.pending');write(tmp,value);tmp.replace(target)
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True);p.add_argument('--export',required=True)
    p.add_argument('--collection',required=True);p.add_argument('--output',required=True)
    p.add_argument('--test-count',type=int,default=9);p.add_argument('--seed',type=int,default=20261104)
    print(create_split(**vars(p.parse_args())))

if __name__=='__main__':main()
