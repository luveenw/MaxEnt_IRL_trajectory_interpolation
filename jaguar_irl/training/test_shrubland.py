"""Candidate-year identity and strict finite exact-grid fraction validation."""
from pathlib import Path
import numpy as np
import pytest
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from .shared_storage import read,write
from .shrubland import make_plan,prepare,convert,RECIPE
from .test_shared import checkpoint_with_maps


def test_cache_plan_keeps_all_group_years_and_pins_source(tmp_path):
    cp,groups,_,_,_=checkpoint_with_maps(tmp_path)
    p=make_plan(cp,'WIN-C01',{'asset_fingerprint':'one'})
    assert p['representative_years'] is None and p['trajectory_year_filter'] is None
    assert p['job_count']==len({(j['group_id'],j['year']) for j in p['groups'].values()})
    assert p['job_count']>len(groups)
    p2=make_plan(cp,'WIN-C01',{'asset_fingerprint':'two'})
    assert all(p['groups'][k]['product_key']!=p2['groups'][k]['product_key'] for k in p['groups'])
    bundle=prepare(cp,tmp_path/'jobs','WIN-C01')
    original=(bundle/'plan.json').read_bytes()
    assert prepare(cp,bundle,'WIN-C01')==bundle and (bundle/'plan.json').read_bytes()==original


def fixture(tmp_path,value=.5,coverage=1,shift=0):
    import rasterio
    from affine import Affine
    b=tmp_path/'jobs';b.mkdir()
    g=dict(crs='EPSG:32721',bounds=[500000,8000000,501000,8001000],rows=2,cols=2,cell_size_m=500,grid_key='test')
    j=dict(group_id='G1',year=2005,grid=g,grid_key='test',product_key='product',export_prefix='test',crs_transform=[500,0,500000,0,-500,8001000])
    write(b/'plan.json',dict(groups={'G1_2005':j},recipe=RECIPE))
    (b/'extract_shrubland.js').write_text('// synthetic fixture')
    write(b/'bundle.json',dict(plan_id=digest(read(b/'plan.json')),files={p.name:file_hash(p) for p in b.iterdir()}))
    t=tmp_path/'test.tif'
    with rasterio.open(t,'w',driver='GTiff',height=2,width=2,count=2,dtype='float32',crs=g['crs'],transform=Affine(500,0,500000+shift,0,-500,8001000),nodata=-9999) as ds:
        ds.write(np.full((2,2),value,dtype='float32'),1);ds.write(np.full((2,2),coverage,dtype='float32'),2)
    return b,t


def test_zero_fraction_is_valid_and_recovery_checks_identity(tmp_path):
    b,t=fixture(tmp_path,value=0)
    out=convert(b,'G1_2005',t,tmp_path/'product')
    assert (np.load(out/'shrubland_fraction.npy')==0).all()
    assert convert(b,'G1_2005',t,out)==out
    np.save(out/'shrubland_fraction.npy',np.ones((2,2)))
    with pytest.raises(ValueError,match='changed'):convert(b,'G1_2005',t,out)


@pytest.mark.parametrize('kw,error',[({'value':1.001},'interval'),({'value':-.001},'interval'),({'value':float('nan')},'nonfinite'),({'coverage':.99},'coverage'),({'shift':250},'Transform')])
def test_bad_rasters_fail_without_partial_publication(tmp_path,kw,error):
    b,t=fixture(tmp_path,**kw)
    with pytest.raises(ValueError,match=error):convert(b,'G1_2005',t,tmp_path/'product')
    assert not (tmp_path/'product').exists()
