import numpy as np
import pytest
from .globpop_density import aggregate,build_overlaps


def fixture():
    raw=dict(density=np.array([[1e-8,np.nan,7.]]),density_mask=np.ones((1,3)),
             x=np.array([[0,1,2]]),y=np.zeros((1,3)),landscan_count=np.zeros((1,3)),landscan_mask=np.ones((1,3)))
    overlaps=dict(native=np.array([0,0,1,1]),target=np.array([0,1,1,2]),area=np.array([100.,40.,60.,100.]),
                  projected_area=np.array([100.,40.,60.,100.]),area_sum=np.array([100.,100.,100.]),shape=np.array([1,3]))
    return raw,overlaps


def test_preserves_sparse_density_and_weighted_boundary_without_renormalizing():
    raw,o=fixture();a,q=aggregate(raw,o,[(1,0)])
    np.testing.assert_allclose(a[0,0],[1e-8,4e-9,0],rtol=1e-15)
    np.testing.assert_allclose(a[2,0],[0,.6,1])
    assert q['native_fallback_pixels']==1 and q['fallback_cells']==2
    assert q['fallback_physical_area_m2']==160
    assert raw['density'][0,0]==1e-8 and np.isnan(raw['density'][0,1])


def test_guarded_missing_scope_and_actual_zero_source():
    raw,o=fixture()
    with pytest.raises(ValueError,match='approved scope'):aggregate(raw,o,[])
    raw['landscan_count'][0,1]=1
    with pytest.raises(ValueError,match='LandScan count0'):aggregate(raw,o,[(1,0)])
    raw['landscan_count'][0,1]=0;raw['landscan_mask'][0,1]=0
    with pytest.raises(ValueError,match='LandScan count0'):aggregate(raw,o,[(1,0)])


def test_bad_bbox_corner_does_not_trigger_fill():
    raw,o=fixture();raw['density'][0,2]=np.nan
    aggregate(raw,o,[(1,0)])
    raw['density'][0,1]=0
    with pytest.raises(ValueError,match='approved scope'):aggregate(raw,o,[(1,0)])


def test_curved_native_polygons_partition_metric_cells():
    grid=dict(crs='EPSG:32721',bounds=[431000.,8020500.,432000.,8021500.],cell_size_m=500.,rows=2,cols=2)
    xs,ys=np.meshgrid(np.arange(14680,14700),np.arange(12920,12955))
    o=build_overlaps(grid,[1/120,0,-180,0,-1/120,90],xs,ys)
    raw=dict(density=np.full(xs.shape,2.5),density_mask=np.ones(xs.shape),x=xs,y=ys,
             landscan_count=np.zeros(xs.shape),landscan_mask=np.ones(xs.shape))
    a,_=aggregate(raw,o,[])
    np.testing.assert_allclose(a[0],2.5);np.testing.assert_allclose(a[3],1)
    assert np.max(abs(o['area_sum']/o['target_area']-1))<2e-7


def test_finite_negative_observation_cannot_be_reclassified_as_missing():
    raw,o=fixture();raw['density'][0,1]=-1
    with pytest.raises(ValueError,match='Finite negative'):
        aggregate(raw,o,[(1,0)])
