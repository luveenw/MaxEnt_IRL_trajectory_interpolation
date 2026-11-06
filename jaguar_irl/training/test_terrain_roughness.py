"""Spatial integrity and incomplete-data rejection, independent of live EE access."""
import json

import numpy as np
import pytest

from jaguar_irl.data.pantanal_checkpoint import digest, file_hash
from .shared_storage import read, write
from .terrain_roughness import RECIPE, check_pixels, convert, make_plan, prepare
from .test_shared import checkpoint_with_maps


def test_plan_uses_canonical_grids_without_split_or_year(tmp_path):
    checkpoint, groups, _, _, _ = checkpoint_with_maps(tmp_path)
    plan = make_plan(checkpoint, 'WIN-C01')
    assert sorted(plan['groups']) == sorted(groups)
    assert plan['representative_year'] is None and plan['trajectory_year_filter'] is None
    assert len({j['product_key'] for j in plan['groups'].values()}) == len(groups)
    for job in plan['groups'].values():
        grid=job['grid']; x,_,_,y=grid['bounds']
        assert job['crs_transform']==[500,0,x,0,-500,y]
    output=prepare(checkpoint,tmp_path/'jobs','WIN-C01')
    original=(output/'plan.json').read_bytes()
    assert prepare(checkpoint,output,'WIN-C01')==output
    assert (output/'plan.json').read_bytes()==original
    assert 'GROUP_IDS = [PLAN.default_pilot_group]' in (output/'extract_roughness.js').read_text()


def raster_bundle(tmp_path, *, shift=0, coverage=1, value=3):
    rasterio=pytest.importorskip('rasterio')
    from affine import Affine
    bundle=tmp_path/'jobs'; bundle.mkdir()
    grid=dict(crs='EPSG:32721',bounds=[500000,8000000,501000,8001000],
              rows=2,cols=2,cell_size_m=500,grid_key='grid_test')
    job=dict(grid=grid,grid_key='grid_test',product_key='test',export_prefix='test',
             crs_transform=[500,0,500000,0,-500,8001000])
    write(bundle/'plan.json',dict(groups={'G001':job},recipe=RECIPE))
    (bundle/'extract_roughness.js').write_text('// synthetic export fixture')
    write(bundle/'bundle.json',dict(plan_id=digest(read(bundle/'plan.json')),
          files={p.name:file_hash(p) for p in bundle.iterdir()}))
    tif=tmp_path/'test.tif'
    with rasterio.open(tif,'w',driver='GTiff',height=2,width=2,count=2,dtype='float32',
                       crs=grid['crs'],transform=Affine(500,0,500000+shift,0,-500,8001000),nodata=-9999) as ds:
        ds.write(np.full((2,2),value,dtype='float32'),1)
        ds.write(np.full((2,2),coverage,dtype='float32'),2)
    return bundle,tif


def test_converter_preserves_zero_and_original_georeferencing(tmp_path):
    bundle,tif=raster_bundle(tmp_path,value=0)
    output=convert(bundle,'G001',tif,tmp_path/'product')
    array=np.load(output/'roughness.npy',allow_pickle=False)
    assert array.shape==(2,2) and np.all(array==0)
    assert (output/'source.tif').read_bytes()==tif.read_bytes()
    first=(output/'validation.json').read_bytes()
    assert convert(bundle,'G001',tif,output)==output
    assert (output/'validation.json').read_bytes()==first
    np.save(output/'roughness.npy',np.ones((2,2)))
    with pytest.raises(ValueError,match='NPY differs'):
        convert(bundle,'G001',tif,output)


@pytest.mark.parametrize('options,error',[
    ({'shift':250},'transform'), ({'coverage':0.999},'coverage'),
    ({'value':-9999},'missing'), ({'value':float('nan')},'nonfinite'),
    ({'value':-1},'nonnegative'),
])
def test_converter_rejects_shifted_or_incomplete_products(tmp_path,options,error):
    bundle,tif=raster_bundle(tmp_path,**options)
    with pytest.raises(ValueError,match=error):
        convert(bundle,'G001',tif,tmp_path/'bad-product')
    assert not (tmp_path/'bad-product').exists()


def test_converter_refuses_changed_bundle(tmp_path):
    bundle,tif=raster_bundle(tmp_path)
    plan=read(bundle/'plan.json'); plan['recipe']['source']='different/source'
    write(bundle/'plan.json',plan)
    with pytest.raises(ValueError,match='hash differs'):
        convert(bundle,'G001',tif,tmp_path/'bad-product')
