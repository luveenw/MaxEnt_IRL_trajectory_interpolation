"""Bounded temporal-consensus repair contracts and preservation of observed QA."""
from pathlib import Path
import numpy as np
import pytest
from .mapbiomas_temporal_repair import check_pixels,convert,build_ee_image,HERE,make_plan


def fixture():
    a=np.zeros((9,35,37),dtype='float32');a[2]=1;a[3]=1;a[7]=1
    a[8,20,13]=.003405869;a[3,20,13]-=a[8,20,13];a[7,20,13]-=a[8,20,13]
    return a


def test_observed_and_imputed_support_remain_separate():
    a=fixture();check_pixels(a,np.ones(a.shape,dtype=bool))
    assert a[7,20,13]<1 and a[2,20,13]==1
    bad=a.copy();bad[7]=1
    with pytest.raises(ValueError):check_pixels(bad,np.ones(a.shape,dtype=bool))
    bad=a.copy();bad[3]=1
    with pytest.raises(ValueError,match='Observed source'):check_pixels(bad,np.ones(a.shape,dtype=bool))


def test_imputation_cannot_escape_approved_cell_or_area():
    a=fixture();a[8,21,13]=a[8,20,13];a[7,21,13]-=a[8,21,13];a[3,21,13]-=a[8,21,13]
    with pytest.raises(ValueError,match='escaped'):check_pixels(a,np.ones(a.shape,dtype=bool))
    a=fixture();a[8,20,13]=.01;a[7,20,13]=.99;a[3,20,13]=.99
    with pytest.raises(ValueError,match='area differs'):check_pixels(a,np.ones(a.shape,dtype=bool))


def test_runtime_rejects_other_groups_and_years():
    with pytest.raises(ValueError,match='scope'):build_ee_image(None,{'year':2010,'group_id':'G316'})
    with pytest.raises(ValueError,match='scope'):build_ee_image(None,{'year':2011,'group_id':'G115'})


def test_converter_rejects_half_cell_shift_and_preserves_parent_lineage(tmp_path):
    import rasterio
    from affine import Affine
    bundle=HERE/'jobs';plan=make_plan();j=plan['groups']['G316_2011'];g=j['grid'];a=fixture()
    f=tmp_path/(j['export_prefix']+'.tif')
    def emit(shift=0):
        tr=j['crs_transform'].copy();tr[2]+=shift
        with rasterio.open(f,'w',driver='GTiff',width=g['cols'],height=g['rows'],count=9,dtype='float32',crs=g['crs'],transform=Affine(*tr),nodata=-9999) as ds:ds.write(a)
    emit();out=convert(bundle,f,tmp_path/'product')
    assert np.array_equal(np.load(out/'grassland_fraction.npy'),a[0])
    assert convert(bundle,f,out)==out
    from .shared_storage import read
    v=read(out/'validation.json');assert v['original_product_key']==plan['original_product_key']
    assert v['observed_coverage_min']<v['effective_coverage_min']
    emit(250)
    with pytest.raises(ValueError,match='transform'):convert(bundle,f,tmp_path/'shifted')
