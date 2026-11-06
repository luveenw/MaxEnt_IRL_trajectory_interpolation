"""Bounded GEE small-raster retrieval, validation and checksum-verified Drive upload.

Signed download URLs and OAuth tokens are never persisted or printed. This is
interactive EE computation; its EECU usage is not available from batch status.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
import time
import requests

from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from .shared_storage import locked,read,sync_dir,write


def _now(): return datetime.now(timezone.utc).isoformat()


def _save(path,state):
    pending=path.with_name('.'+path.name+'.pending')
    write(pending,state);os.replace(pending,path);sync_dir(path.parent)


def acquire_direct(ee,image,job,folder_id,output,ledger,source_identity,validate,project='perceptive-ivy-780'):
    """Retrieve one NEW/unsubmitted job and return a durable direct-job record.

    `job` has grid, crs_transform, export_prefix and product_key. `validate(tif)`
    must reject invalid products and may return its immutable product directory.
    Existing batch ledgers must be handled by their batch driver, never here.
    Uncertain Drive uploads are reconciled by exact filename+content, not retried
    blindly. Caller must limit concurrency and verify source identity separately.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    output,ledger=Path(output).resolve(),Path(ledger).resolve()
    output.mkdir(parents=True,exist_ok=True)
    grid=job['grid'];rows,cols=grid['rows'],grid['cols']
    if max(rows,cols)>10000 or rows*cols*len(image.bandNames().getInfo())*8>32*1024*1024:
        raise ValueError('Output exceeds conservative GEE small-download limits; use batch')
    params={'crs':grid['crs'],'crs_transform':job['crs_transform'],
            'dimensions':[cols,rows],'format':'GEO_TIFF','name':job['export_prefix']}
    identity=dict(product_key=job['product_key'],project=project,source_identity=source_identity,
                  request_graph_sha256=hashlib.sha256(image.serialize().encode()).hexdigest(),
                  request_parameters=params,drive_folder_id=folder_id)
    target=output/(job['export_prefix']+'.tif')
    with locked(ledger.parent):
        if ledger.exists():
            record=read(ledger)
            if record.get('acquisition_kind')!='gee_direct_download':raise ValueError('Existing ledger belongs to a batch task; resume it first')
            if any(record.get(k)!=v for k,v in identity.items()):raise ValueError('Direct request identity changed')
        else:
            if target.exists():raise ValueError('Untracked TIFF already exists; reconcile before direct retrieval')
            record=dict(schema='gee_direct_acquisition/1',acquisition_kind='gee_direct_download',
                        status='download_intent',started_utc=_now(),online_eecu_usage_seconds=None,
                        online_eecu_usage_measured=False,helper_sha256=file_hash(__file__),**identity)
            _save(ledger,record)
        prior_status=record['status'];began=time.monotonic()
        if target.exists():
            if record.get('download_sha256') and file_hash(target)!=record['download_sha256']:
                raise ValueError('Existing direct TIFF differs from recorded checksum')
        else:
            if prior_status not in ('download_intent','download_failed'):
                raise ValueError('Previously downloaded TIFF is missing; investigate rather than recompute')
            signed_url=image.getDownloadURL(dict(params))
            fd,pending=tempfile.mkstemp(prefix='.pending-direct-',dir=output)
            try:
                try:
                    response=requests.get(signed_url,timeout=300)
                    if response.status_code!=200:raise RuntimeError('Non-success response')
                except Exception:
                    record['status']='download_failed';record['error']='GEE direct request failed; URL suppressed'
                    _save(ledger,record)
                    raise RuntimeError('GEE direct download failed; signed URL suppressed') from None
                with os.fdopen(fd,'wb') as handle:
                    handle.write(response.content);handle.flush();os.fsync(handle.fileno())
                fd=None
                os.replace(pending,target);sync_dir(output)
            finally:
                if fd is not None:os.close(fd)
                Path(pending).unlink(missing_ok=True)
            record.update(status='downloaded',downloaded_utc=_now(),download_sha256=file_hash(target),
                          download_size_bytes=target.stat().st_size)
            _save(ledger,record)
        try:
            product=validate(target)
        except Exception:
            record['status']='validation_failed';_save(ledger,record);raise
        md5=hashlib.md5(target.read_bytes()).hexdigest()
        credentials=ee.data.get_persistent_credentials()
        drive=build('drive','v3',credentials=credentials,cache_discovery=False)
        if not all(c.isalnum() or c in '-_' for c in folder_id):raise ValueError('Invalid pinned folder identifier')
        escaped=target.name.replace('\\','\\\\').replace("'","\\'")
        q=f"trashed=false and '{folder_id}' in parents and name='{escaped}'"
        found=drive.files().list(q=q,fields='files(id,name,size,md5Checksum,parents),nextPageToken',pageSize=100).execute()
        if len(found['files'])>1 or found.get('nextPageToken'):raise ValueError('Duplicate Drive output names; reconcile manually')
        if found['files']:
            remote=found['files'][0]
        else:
            if prior_status in ('upload_intent','upload_uncertain','COMPLETED'):
                raise ValueError('Prior upload is not visible; reconcile before any retry')
            record.update(status='upload_intent',validated_product=str(product),download_sha256=file_hash(target),download_size_bytes=target.stat().st_size)
            _save(ledger,record)
            try:
                remote=drive.files().create(body={'name':target.name,'parents':[folder_id]},
                    media_body=MediaFileUpload(str(target),mimetype='image/tiff',resumable=False),
                    fields='id,name,size,md5Checksum,parents').execute()
            except Exception:
                record['status']='upload_uncertain';_save(ledger,record)
                raise RuntimeError('Drive upload response uncertain; reconcile exact filename/checksum before retry') from None
        if remote.get('md5Checksum')!=md5 or int(remote.get('size',-1))!=target.stat().st_size or folder_id not in remote.get('parents',[]):
            raise ValueError('Drive content or destination does not match validated TIFF')
        write(target.with_name(target.name+'.drive.json'),remote)
        record.update(status='COMPLETED',drive_file=remote,validated_product=str(product),download_sha256=file_hash(target),
                      download_size_bytes=target.stat().st_size,download_md5=md5)
        if prior_status!='COMPLETED':record.update(completed_utc=_now(),wall_seconds_this_attempt=time.monotonic()-began)
        _save(ledger,record)
        return record
