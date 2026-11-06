"""Contracts for source priority, source completeness and paired class fractions."""
from pathlib import Path
import numpy as np
import pytest
from .mapbiomas_landcover import choose_pixel,make_plan,prepare,convert,check_pixels

CP=Path(__file__).resolve().parents[2]/'analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0'


def test_candidate_cache_exactly_matches_membership_and_source_identity(tmp_path):
    plan=make_plan(CP,source_snapshot={'asset_fingerprint':'source1'})
    assert plan['group_count']==13 and plan['job_count']==24
    assert plan['representative_years'] is None and plan['trajectory_year_filter'] is None
    assert {j['year'] for j in plan['groups'].values()}=={2005,2006,2008,2009,2010,2011,2012,2013,2014,2015}
    assert {j['year'] for j in plan['groups'].values() if j['group_id']=='G115'}=={2005,2006}
    assert all(j['crs_transform']==[500,0,j['grid']['bounds'][0],0,-500,j['grid']['bounds'][3]] for j in plan['groups'].values())
    other=make_plan(CP,source_snapshot={'asset_fingerprint':'source2'})
    assert all(plan['groups'][k]['product_key']!=other['groups'][k]['product_key'] for k in plan['groups'])
    a=prepare(CP,tmp_path/'bundle')
    before={p.name:p.read_bytes() for p in a.iterdir()}
    assert prepare(CP,a)==a
    assert before=={p.name:p.read_bytes() for p in a.iterdir()}


@pytest.mark.parametrize('values,expected',[
    ({'brazil':15,'paraguay':12,'bolivia':11},('brazil',15,True)),
    ({'brazil':0,'paraguay':11,'bolivia':12},('paraguay',11,True)),
    ({'brazil':27,'paraguay':None,'bolivia':12},('bolivia',12,True)),
    ({'brazil':999,'paraguay':12},('brazil',999,False)),
    ({'chaco':26},('chaco',26,True)),
    ({'chaco':12},(None,12,False)),
])
def test_selection_never_falls_through_for_valid_nontarget_or_unknown(values,expected):
    assert choose_pixel(values)==expected


def test_source_fractions_and_complete_coverage_are_required():
    a=np.zeros((7,2,3),dtype=np.float32);a[2]=1;a[6]=1
    check_pixels(a,np.ones(a.shape,dtype=bool)) # Chaco water is valid, both target fractions zero.
    bad=a.copy();bad[2,0,0]=.99
    with pytest.raises(ValueError,match='Incomplete'):check_pixels(bad,np.ones(a.shape,dtype=bool))
    bad=a.copy();bad[6,0,0]=.9
    with pytest.raises(ValueError,match='sum'):check_pixels(bad,np.ones(a.shape,dtype=bool))
    bad=a.copy();bad[0]=.8;bad[1]=.4
    with pytest.raises(ValueError,match='Exclusive'):check_pixels(bad,np.ones(a.shape,dtype=bool))
    bad=a.copy();bad[0]=.1 # All area is fallback water, so a target cannot occupy any of it.
    with pytest.raises(ValueError,match='Exclusive'):check_pixels(bad,np.ones(a.shape,dtype=bool))
    bad=a.copy();bad[0,0,0]=1.01
    with pytest.raises(ValueError,match='interval'):check_pixels(bad,np.ones(a.shape,dtype=bool))


def test_converter_keeps_zero_and_rejects_shift_missing_and_changed_bundle(tmp_path):
    import rasterio
    from affine import Affine
    bundle=prepare(CP,tmp_path/'bundle');plan=make_plan(CP);job_id=plan['default_pilot_job'];job=plan['groups'][job_id];g=job['grid']
    data=np.zeros((7,g['rows'],g['cols']),dtype='float32');data[0]=.2;data[1]=.3;data[2]=1;data[3]=1
    tif=tmp_path/(job['export_prefix']+'.tif')
    def emit(a,shift=0):
        tr=job['crs_transform'].copy();tr[2]+=shift
        with rasterio.open(tif,'w',driver='GTiff',height=g['rows'],width=g['cols'],count=7,dtype='float32',crs=g['crs'],transform=Affine(*tr),nodata=-9999) as ds:ds.write(a)
    emit(data)
    out=convert(bundle,job_id,tif,tmp_path/'product')
    assert np.array_equal(np.load(out/'grassland_fraction.npy'),data[0])
    assert convert(bundle,job_id,tif,out)==out
    emit(data,250)
    with pytest.raises(ValueError,match='Transform'):convert(bundle,job_id,tif,tmp_path/'badshift')
    bad=data.copy();bad[0,0,0]=-9999;emit(bad)
    with pytest.raises(ValueError,match='Missing'):convert(bundle,job_id,tif,tmp_path/'badmissing')
    emit(data);(bundle/'extract_landcover.js').write_text('changed')
    with pytest.raises(ValueError,match='hash'):convert(bundle,job_id,tif,tmp_path/'badbundle')
