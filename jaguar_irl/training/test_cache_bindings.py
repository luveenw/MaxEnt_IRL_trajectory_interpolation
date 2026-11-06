from pathlib import Path
import numpy as np
import pytest
from . import cache_bindings as cb
from .shared_storage import read,write
from jaguar_irl.data.pantanal_checkpoint import file_hash
from .test_shared import checkpoint_with_maps
from .shared import bind,prepare


def inputs(tmp_path):
    grid=dict(grid_key='gridA');features={}
    for name in cb.FEATURES:
        path=tmp_path/name;path.mkdir();array=np.array([[0.,0.],[0.,0.],[10.,10.]])
        if name=='shrubland':array[:]=3
        np.save(path/'feature.npy',array)
        validation=path/'validation.json';write(validation,dict(grid=grid,product_key='product-'+name))
        features[name]=dict(path=str(path/'feature.npy'),sha256=file_hash(path/'feature.npy'),units='test units',validation_path=str(validation),validation_sha256=file_hash(validation))
    inventory=tmp_path/'inventory.json';write(inventory,dict(group_years={'A_2010':dict(grid_key='gridA',shape=[3,2],features=features)}))
    long=np.array([[i%2,0,i]for i in range(11)])
    short=np.array([[2,0,0],[2,1,1],[2,0,2]])
    routes=[]
    for ident,a in [('1',long),('2',short)]:
        path=tmp_path/(ident+'.npy');np.save(path,a)
        routes.append(dict(individual_id=ident,group_id='A',trajectory_id='route'+ident,path=str(path),sha256=file_hash(path)))
    base=dict(checkpoint_sha256='checkpoint',export_sha256='export',season='spring',requested_groups=['A'],groups_without_split_evidence=[],temporal_scope='static_season_across_years',groups={'A':dict(grid_key='gridA',representative_season_year=2010)},trajectories=routes)
    train=tmp_path/'train.json';test=tmp_path/'test.json';write(train,{**base,'split':'train'});write(test,{**base,'split':'test'})
    return train,test,inventory


def test_scaling_is_equal_animal_and_train_only(tmp_path):
    train,test,inventory=inputs(tmp_path);out=cb.fit_scaling(train,inventory,tmp_path/'scaling.json');s=read(out)
    assert s['features']['roughness']['offset']==5
    assert s['features']['roughness']['scale']==5
    assert s['features']['shrubland']['constant_in_training']
    assert s['features']['shrubland']['scale']==1
    assert s['departure_counts']=={'1':10,'2':2}
    with pytest.raises(ValueError,match='train plan'):cb.fit_scaling(test,inventory,tmp_path/'bad.json')


def test_bounds_use_unvisited_training_cells_and_freeze_for_test(tmp_path):
    train,test,inventory=inputs(tmp_path);index=read(inventory)
    for name,entry in index['group_years']['A_2010']['features'].items():
        a=np.zeros((3,2));a[2,1]=50 if name in cb.FEATURES[:2] else 1
        np.save(entry['path'],a);entry['sha256']=file_hash(entry['path'])
    write(inventory,index)
    # Only zero-valued cells are visited; the full-map upper bound is still 50.
    plan=read(train);plan['trajectories']=plan['trajectories'][:1];write(train,plan)
    out=cb.fit_bounds(train,inventory,tmp_path/'bounds.json');s=read(out)
    assert s['features']['roughness']==dict(offset=50.,scale=50.)
    assert s['features']['grassland']==dict(offset=1.,scale=1.)
    a=cb.resolve(train,inventory,tmp_path/'a.json',secondary_plan=test,scaling_file=out)
    b=cb.resolve(test,inventory,tmp_path/'b.json',secondary_plan=train,scaling_file=out)
    assert read(a)['features']==read(b)['features']
    assert (100-s['features']['roughness']['offset'])/s['features']['roughness']['scale']==1
    with pytest.raises(ValueError,match='train plan'):cb.fit_bounds(test,inventory,tmp_path/'bad.json')


def test_resolver_reuses_cache_and_scaling_across_contexts(tmp_path):
    train,test,inventory=inputs(tmp_path);scale=cb.fit_scaling(train,inventory,tmp_path/'scale.json')
    a=cb.resolve(train,inventory,tmp_path/'train-binding.json',secondary_plan=test,scaling_file=scale)
    b=cb.resolve(test,inventory,tmp_path/'test-binding.json',secondary_plan=train,scaling_file=scale)
    assert read(a)['features']==read(b)['features']
    assert read(a)['groups']['A']['files']['roughness']['path']==read(b)['groups']['A']['files']['roughness']['path']
    assert read(a)['groups']['A']['files']['roughness']['source_epoch']==2000
    altered=read(train);altered['trajectories']=[];write(tmp_path/'different.json',altered)
    with pytest.raises(ValueError,match='match this training plan'):
        cb.resolve(test,inventory,tmp_path/'bad.json',secondary_plan=tmp_path/'different.json',scaling_file=scale)
    with pytest.raises(ValueError,match='Choose explicit'):cb.resolve(train,inventory,tmp_path/'missing.json')


def test_inactive_maps_can_use_other_context_without_selecting_active_year(tmp_path):
    train,test,inventory=inputs(tmp_path);t=read(train);t['groups']={};t['groups_without_split_evidence']=['A'];write(train,t)
    out=cb.resolve(train,inventory,tmp_path/'binding.json',secondary_plan=test,identity=True)
    f=read(out)['groups']['A']['files']['roughness']
    assert f['source_context_split']=='test' and f['active_for_primary_split'] is False


def test_explicit_profiles_preserve_original_default_and_pin_preparation(tmp_path):
    checkpoint,groups,specpath,default,export=checkpoint_with_maps(tmp_path)
    first=bind(checkpoint,specpath,binding_dir=tmp_path/'train-profile')
    spec=read(specpath);f=next(iter(spec['groups'][groups[0]]['files'].values()))
    # Distinct profile can carry another scaling contract without touching the
    # default or first immutable profile. No real fitting is run here.
    spec['features'][0]['scale']=2;write(tmp_path/'test-spec.json',spec)
    second=bind(checkpoint,tmp_path/'test-spec.json',binding_dir=tmp_path/'test-profile')
    assert read(first)['features'][0]['scale']==1
    assert read(second)['features'][0]['scale']==2
    assert (checkpoint/'covariates/current/state.json').resolve()==default
    run=tmp_path/'explicit-run'
    prepare(checkpoint,run,collection='WIN-C01',export=export,split='unassigned',binding_state=first)
    assert (run/read(run/'plan.json')['binding_path']).resolve()==first
    assert read(run/'plan.json')['bindings']['features']==read(first)['features']
    assert read(run/'plan.json')['optimizer']['iterations'] is None
