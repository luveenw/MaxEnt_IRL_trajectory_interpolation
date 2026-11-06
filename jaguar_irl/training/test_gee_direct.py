"""Direct retrieval never uploads unvalidated data or duplicates an uncertain upload."""
from types import SimpleNamespace as NS
from pathlib import Path
import hashlib
import pytest
from . import gee_direct
from .shared_storage import read,write


def context(monkeypatch,tmp_path,remote=None,upload_failure=False):
    import googleapiclient.discovery
    payload=b'validated fixture bytes';events=[]
    metadata={'id':'drive1','name':'product.tif','size':str(len(payload)),
              'md5Checksum':hashlib.md5(payload).hexdigest(),'parents':['folder1']}
    class Files:
        def list(self,**kw):return NS(execute=lambda:{'files':list(remote or [])})
        def create(self,**kw):
            def execute():
                events.append('upload')
                if upload_failure:raise RuntimeError('lost response')
                return metadata
            return NS(execute=execute)
    monkeypatch.setattr(googleapiclient.discovery,'build',lambda *a,**kw:NS(files=lambda:Files()))
    monkeypatch.setattr(gee_direct.requests,'get',lambda *a,**kw:NS(status_code=200,content=payload))
    ee=NS(data=NS(get_persistent_credentials=lambda:None))
    def download_url(params):
        params['image']=object() # Real EE client mutates the caller parameter dictionary.
        params['dimensions'].append(999)
        params['crs_transform'][0]=-123 # Deep copying also protects nested source-job values.
        return 'https://example.test/signed?secret=not-logged'
    im=NS(bandNames=lambda:NS(getInfo=lambda:['fraction','valid']),serialize=lambda:'fixed_graph',getDownloadURL=download_url)
    j=dict(grid={'rows':2,'cols':2,'crs':'EPSG:32721'},crs_transform=[500,0,0,0,-500,1000],export_prefix='product',product_key='key')
    def validate(p):events.append('validate');return tmp_path/'product'
    return ee,im,j,validate,metadata,events


def test_validate_precedes_upload_and_metadata_excludes_signed_url(monkeypatch,tmp_path):
    e,i,j,v,meta,events=context(monkeypatch,tmp_path)
    ledger=tmp_path/'tasks/job.json'
    result=gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert events==['validate','upload']
    assert result['status']=='COMPLETED' and result['online_eecu_usage_seconds'] is None
    assert 'task_id' not in result and 'secret' not in ledger.read_text()
    assert result['drive_file']==meta
    assert result['request_parameters']['dimensions']==[2,2] and result['request_parameters']['crs_transform'][0]==500
    assert result['completed_by_helper_sha256']==gee_direct.HELPER_SHA256


def test_validation_failure_prevents_any_upload(monkeypatch,tmp_path):
    e,i,j,v,meta,events=context(monkeypatch,tmp_path)
    def reject(p):raise ValueError('bad raster')
    with pytest.raises(ValueError):gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',tmp_path/'tasks/job.json','source',reject)
    assert 'upload' not in events


def test_lost_upload_response_never_causes_blind_duplicate(monkeypatch,tmp_path):
    e,i,j,v,meta,events=context(monkeypatch,tmp_path,upload_failure=True)
    ledger=tmp_path/'tasks/job.json'
    with pytest.raises(RuntimeError,match='uncertain'):gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert read(ledger)['status']=='upload_uncertain'
    with pytest.raises(ValueError,match='reconcile'):gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert events.count('upload')==1
    e,i,j,v,meta,events=context(monkeypatch,tmp_path,remote=[meta])
    result=gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert result['status']=='COMPLETED' and 'upload' not in events


def test_existing_batch_ledger_is_not_recomputed(monkeypatch,tmp_path):
    e,i,j,v,meta,events=context(monkeypatch,tmp_path)
    ledger=tmp_path/'tasks/job.json';ledger.parent.mkdir();write(ledger,{'task_id':'batch1','status':'RUNNING'})
    with pytest.raises(ValueError,match='batch'):gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert not events


def test_resume_preserves_initial_attempt_hash_and_records_completion_helper(monkeypatch,tmp_path):
    e,i,j,v,meta,events=context(monkeypatch,tmp_path,upload_failure=True)
    ledger=tmp_path/'tasks/job.json'
    with pytest.raises(RuntimeError):gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    record=read(ledger);record['helper_sha256']='historical_first_attempt';record['helper_sha256_history']=['historical_first_attempt'];write(ledger,record)
    e,i,j,v,meta,events=context(monkeypatch,tmp_path,remote=[meta])
    result=gee_direct.acquire_direct(e,i,j,'folder1',tmp_path/'downloads',ledger,'source',v)
    assert result['helper_sha256']=='historical_first_attempt'
    assert result['helper_sha256_history']==['historical_first_attempt',gee_direct.HELPER_SHA256]
    assert result['completed_by_helper_sha256']==gee_direct.HELPER_SHA256
