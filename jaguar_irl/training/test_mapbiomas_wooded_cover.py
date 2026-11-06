"""Coverage and repair semantics for a new ecological feature recipe."""
import numpy as np
import pytest
from .mapbiomas_wooded_cover import check_pixels,make_plan,RECIPE
from .shared_storage import read
from pathlib import Path


def valid_pixels():
    x=np.zeros((8,2,2),dtype=np.float32);x[0]=.4;x[1]=1;x[2]=1;x[6]=1
    return x


def test_source_provenance_and_coverage_are_separate_from_class_fraction():
    x=valid_pixels();check_pixels(x,np.ones_like(x,bool),'G050_2008')
    x[2,0,0]=.5
    with pytest.raises(ValueError,match='Source fractions'):check_pixels(x,np.ones_like(x,bool),'G050_2008')


def test_missing_coverage_cannot_be_zero_filled():
    x=valid_pixels();x[1,0,0]=.99
    with pytest.raises(ValueError,match='Incomplete'):check_pixels(x,np.ones_like(x,bool),'G050_2008')
    x=valid_pixels();mask=np.ones_like(x,bool);mask[0,0,0]=False
    with pytest.raises(ValueError,match='Missing'):check_pixels(x,mask,'G050_2008')


def test_repair_is_scoped_and_contributes_wooded_area():
    x=np.zeros((8,21,14),np.float32);x[1]=x[2]=x[6]=1
    f=.003405881;x[7,20,13]=f;x[2,20,13]=x[6,20,13]=1-f
    with pytest.raises(ValueError,match='omitted'):check_pixels(x,np.ones_like(x,bool),'G316_2011')
    x[0,20,13]=f;check_pixels(x,np.ones_like(x,bool),'G316_2011')
    with pytest.raises(ValueError,match='Unexpected'):check_pixels(x,np.ones_like(x,bool),'G316_2010')


def test_plan_preserves_24_candidate_epochs_without_split_filter():
    root=Path(__file__).resolve().parents[2]
    cp=root/'analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0'
    snapshot=read(root/'data/pantanal_covariates/spring_mapbiomas_landcover_v1/source_snapshot.json')
    plan=make_plan(cp,snapshot)
    old=read(root/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json')
    assert set(plan['groups'])==set(old['groups']) and len(plan['groups'])==24
    assert all(j['grid']==old['groups'][k]['grid'] for k,j in plan['groups'].items())
    assert RECIPE['selected_classes']==[3,4] and RECIPE['smoothing'] is None
