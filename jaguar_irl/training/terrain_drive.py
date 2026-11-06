"""Download a completed terrain export from an explicitly pinned Drive folder."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

from .shared_storage import locked, read, write, sync_dir
from .terrain_roughness import verify_bundle


def download(bundle, group, folder_id, output):
    import ee
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    plan=verify_bundle(bundle)
    name=plan['groups'][group]['export_prefix']+'.tif'
    output=Path(output).resolve()
    credentials=ee.data.get_persistent_credentials()
    drive=build('drive','v3',credentials=credentials,cache_discovery=False)
    # Google-generated identifiers and planned filenames, never arbitrary query fragments.
    if not all(c.isalnum() or c in '-_' for c in folder_id):
        raise ValueError('Invalid folder identifier')
    escaped=name.replace('\\','\\\\').replace("'","\\'")
    q=f"trashed=false and '{folder_id}' in parents and name='{escaped}'"
    found=drive.files().list(q=q,fields='files(id,name,size,md5Checksum,parents),nextPageToken',pageSize=100).execute()
    if len(found['files'])!=1 or found.get('nextPageToken'):
        raise ValueError('Require exactly one matching completed TIFF in the pinned folder')
    remote=found['files'][0]
    if not remote.get('md5Checksum') or int(remote.get('size',0))<=0:
        raise ValueError('Export is not a complete binary file')
    target=output/name
    sidecar=output/(name+'.drive.json')
    with locked(output):
        if target.exists():
            if hashlib.md5(target.read_bytes()).hexdigest()!=remote['md5Checksum']:
                raise ValueError('Existing download differs from Drive; preserve it and investigate')
            if sidecar.exists() and read(sidecar)!=remote:
                raise ValueError('Drive identity changed for existing download')
            if not sidecar.exists(): write(sidecar,remote)
            return target
        fd,pending=tempfile.mkstemp(prefix='.pending-download-',dir=output)
        try:
            with os.fdopen(fd,'wb') as handle:
                transfer=MediaIoBaseDownload(handle,drive.files().get_media(fileId=remote['id']))
                done=False
                while not done:
                    _,done=transfer.next_chunk()
                handle.flush(); os.fsync(handle.fileno())
            temp=Path(pending)
            if temp.stat().st_size!=int(remote['size']) or hashlib.md5(temp.read_bytes()).hexdigest()!=remote['md5Checksum']:
                raise ValueError('Downloaded size/checksum differs from Drive')
            os.replace(temp,target)
            write(sidecar,remote); sync_dir(output)
        finally:
            Path(pending).unlink(missing_ok=True)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True);parser.add_argument('--group',required=True)
    parser.add_argument('--folder-id',required=True);parser.add_argument('--output',required=True)
    print(download(**vars(parser.parse_args())))


if __name__=='__main__': main()
