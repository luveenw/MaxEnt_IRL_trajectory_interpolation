"""Source/denominator invariants for continuous canopy percent."""
import numpy as np
import pytest
from .tree_cover import check_pixels,make_plan,RECIPE


def data():
 return np.array([[[0.,50.,100.]],[[1.,1.,1.]],[[1.,.25,0.]],[[0.,0.,0.]]],dtype=np.float32)


def test_zero_canopy_and_water_are_valid():
 x=data();check_pixels(x,np.ones_like(x,dtype=bool))


def test_percent_is_not_unit_fraction():
 x=data();check_pixels(x,np.ones_like(x,dtype=bool))
 x[0,0,2]=100.01
 with pytest.raises(ValueError,match='percent range'):check_pixels(x,np.ones_like(x,dtype=bool))


def test_missing_coverage_and_mask_rejected():
 x=data();x[1,0,1]=.99
 with pytest.raises(ValueError,match='coverage'):check_pixels(x,np.ones_like(x,dtype=bool))
 x=data();mask=np.ones_like(x,dtype=bool);mask[0,0,0]=False
 with pytest.raises(ValueError,match='Missing'):check_pixels(x,mask)


def test_water_conflict_and_area_bound_rejected():
 x=data();x[3,0,0]=.001
 with pytest.raises(ValueError,match='nonzero canopy'):check_pixels(x,np.ones_like(x,dtype=bool))
 x=data();x[0,0,0]=1
 with pytest.raises(ValueError,match='nonwater area'):check_pixels(x,np.ones_like(x,dtype=bool))


def test_static_recipe_explicit_semantics():
 assert RECIPE['source_epoch']==2000
 assert RECIPE['threshold'] is None and RECIPE['smoothing'] is None
 assert RECIPE['temporal_filter'] is None and RECIPE['loss_gain_adjustment'] is None
 assert RECIPE['band']=='treecover2000'
