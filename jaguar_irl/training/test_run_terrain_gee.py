"""No-network checks of bounded submission and crash recovery behavior."""
from types import SimpleNamespace as NS
import pytest
from . import run_terrain_gee as runner
from .shared_storage import read, write


def setup_submission(monkeypatch, tmp_path, tasks=(), failure=False):
    bundle=tmp_path/'bundle'; bundle.mkdir(); (bundle/'plan.json').write_text('{}')
    job=dict(export_prefix='unique_product',product_key='product',output_cells=10,
             grid={'bounds':[0,0,1000,2500],'crs':'EPSG:32721'},
             crs_transform=[500,0,0,0,-500,2500])
    plan=dict(default_pilot_group='G1',groups={'G1':job,'G2':dict(job)})
    monkeypatch.setattr(runner,'load_bundle',lambda b:(bundle,plan))
    monkeypatch.setattr(runner,'build_ee_image',lambda e,j:'image')
    started=[]
    def start():
        started.append(True)
        if failure: raise RuntimeError('Response lost')
    task=NS(id='task1',operation_name='op1',start=start)
    ee=NS(Initialize=lambda **kw:None,
          Geometry=NS(Rectangle=lambda *a:'region'),
          batch=NS(Task=NS(list=lambda:list(tasks)),
                   Export=NS(image=NS(toDrive=lambda **kw:task))))
    return ee,bundle,started


def test_submit_once_and_refuse_retries(monkeypatch,tmp_path):
    ee,bundle,started=setup_submission(monkeypatch,tmp_path)
    ledger=tmp_path/'task.json'
    runner.submit(ee,bundle,'project','folder',ledger)
    assert read(ledger)['task_id']=='task1' and started==[True]
    with pytest.raises(ValueError,match='already exists'):
        runner.submit(ee,bundle,'project','folder',ledger)
    assert started==[True]


@pytest.mark.parametrize('task',[
    NS(state='COMPLETED',config={'description':'unique_product'}),
    NS(state='RUNNING',config={'description':'other'}),
    NS(state='CANCEL_REQUESTED',config={'description':'other'}),
])
def test_cloud_duplicates_or_active_tasks_prevent_submission(monkeypatch,tmp_path,task):
    ee,bundle,started=setup_submission(monkeypatch,tmp_path,[task])
    with pytest.raises(ValueError):
        runner.submit(ee,bundle,'project','folder',tmp_path/'task.json')
    assert not started and not (tmp_path/'task.json').exists()


def test_uncertain_submission_is_durable_and_not_retried(monkeypatch,tmp_path):
    ee,bundle,started=setup_submission(monkeypatch,tmp_path,failure=True)
    ledger=tmp_path/'task.json'
    with pytest.raises(RuntimeError): runner.submit(ee,bundle,'project','folder',ledger)
    assert read(ledger)['status'].startswith('submission_uncertain')
    with pytest.raises(ValueError): runner.submit(ee,bundle,'project','folder',ledger)
    assert started==[True]


def test_nonpilot_requires_matching_validation(monkeypatch,tmp_path):
    ee,bundle,started=setup_submission(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match='pilot TIFF'):
        runner.submit(ee,bundle,'project','folder',tmp_path/'task.json',group='G2')
    assert not started


def test_status_recovers_a_task_after_lost_submission_response(tmp_path):
    ledger=tmp_path/'task.json'
    write(ledger,dict(project='project',description='unique_product',task_id=None))
    task=NS(id='task1',config={'description':'unique_product'},
            status=lambda:{'state':'COMPLETED','id':'task1'})
    ee=NS(Initialize=lambda **kw:None,batch=NS(Task=NS(list=lambda:[task])))
    result=runner.status(ee,ledger)
    assert result['status']=='COMPLETED' and read(ledger)['task_id']=='task1'
