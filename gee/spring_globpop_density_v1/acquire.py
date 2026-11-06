"""GEE native retrieval, local physical overlap integration, verified Drive copies.

No coarse-to-fine resampling shortcut:500m products are computed locally from
native angular pixel intersections. Raw source NaNs are retained in NPZ archives.
"""
import argparse,hashlib,json,os,tempfile
from pathlib import Path
import numpy as np
import ee,rasterio
from affine import Affine
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from jaguar_irl.data.pantanal_checkpoint import file_hash,digest
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.globpop_density import build_overlaps,aggregate,BANDS
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;BUNDLE=HERE/'jobs';DATA=ROOT/'data/pantanal_covariates/spring_globpop_density_v1'


def native(ee,job):
    density=ee.Image(job['density_asset']).select('b1');projection=density.projection()
    image=density.rename('density').addBands(density.mask().rename('density_mask')).addBands(ee.Image.pixelCoordinates(projection))
    if job['landscan_asset']:
        # Reproject using the actual image affine, not an assumed annual row offset.
        ls=ee.Image(job['landscan_asset']).select('b1').reproject(projection)
        image=image.addBands(ls.rename('landscan_count')).addBands(ls.mask().rename('landscan_mask'))
    else:
        image=image.addBands(ee.Image.constant(0).rename('landscan_count').reproject(projection)).addBands(ee.Image.constant(0).rename('landscan_mask').reproject(projection))
    region=ee.Geometry.Rectangle(job['grid']['bounds'],job['grid']['crs'],False)
    raw=image.toDouble().sampleRectangle(region,defaultValue=-9999).getInfo()['properties']
    arrays={k:np.array(raw[k],dtype=float)for k in ['density','density_mask','x','y','landscan_count','landscan_mask']}
    shape=arrays['density'].shape
    if any(a.shape!=shape for a in arrays.values()):raise ValueError('Native bands not aligned')
    if not np.all(np.isfinite(arrays['x']))or not np.all(np.isfinite(arrays['y'])):raise ValueError('Missing native coordinates')
    arrays['x']=arrays['x'].astype(np.int64);arrays['y']=arrays['y'].astype(np.int64)
    return arrays


def upload(drive,tif,folder,ledger,product_key):
    ledger.parent.mkdir(parents=True,exist_ok=True)
    md5=hashlib.md5(tif.read_bytes()).hexdigest();size=tif.stat().st_size
    if ledger.exists():
        record=read(ledger)
        if record['product_key']!=product_key or record['sha256']!=file_hash(tif):raise ValueError('Existing upload identity changed')
    else:record=dict(schema='local_overlap_density_drive_upload/1',status='upload_intent',product_key=product_key,sha256=file_hash(tif),filename=tif.name,folder=folder)
    write(ledger,record)
    found=drive.files().list(q=f"trashed=false and '{folder}' in parents and name='{tif.name}'",fields='files(id,name,md5Checksum,size,parents),nextPageToken',pageSize=100).execute()
    if found.get('nextPageToken')or len(found['files'])>1:raise ValueError('Duplicate Drive product')
    if found['files']:remote=found['files'][0]
    else:
        if record['status']in('upload_uncertain','COMPLETED'):raise ValueError('Prior upload not visible; reconcile before retry')
        try:remote=drive.files().create(body={'name':tif.name,'parents':[folder]},media_body=MediaFileUpload(str(tif),mimetype='image/tiff',resumable=False),fields='id,name,md5Checksum,size,parents').execute()
        except Exception:
            record['status']='upload_uncertain';write(ledger,record);raise RuntimeError('Drive upload uncertain; reconcile exact filename and checksum')from None
    if remote['md5Checksum']!=md5 or int(remote['size'])!=size or folder not in remote['parents']:raise ValueError('Drive checksum/destination mismatch')
    record.update(status='COMPLETED',drive_file=remote,md5=md5,size_bytes=size);write(ledger,record);return remote


def run(pilot_only=False):
    plan=read(BUNDLE/'plan.json');config=read(DATA/'cloud_setup.json')
    if file_hash(ROOT/'jaguar_irl/training/globpop_density.py')!=plan['software_sha256']:raise ValueError('Frozen module changed')
    if file_hash(BUNDLE/'approval.json')!=plan['approval_sha256']or file_hash(BUNDLE/'approved_gap_footprints.json')!=plan['gaps_sha256']:raise ValueError('Frozen approval changed')
    ee.Initialize(project=config['project']);ee.data.setDeadline(180000)
    assets={a:ee.data.getAsset(a)for a in plan['source_snapshot']['assets']}
    if digest(assets)!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Pinned source metadata changed')
    drive=build('drive','v3',credentials=ee.data.get_persistent_credentials(),cache_discovery=False)
    ids=[plan['default_pilot_job']]+[k for k in plan['groups']if k!=plan['default_pilot_job']]
    if pilot_only:ids=ids[:1]
    completed=read(DATA/'acquisition.json')['groups']if(DATA/'acquisition.json').exists()else{}
    for key in ids:
        j=plan['groups'][key];g=j['grid'];rawdir=DATA/'native';rawdir.mkdir(exist_ok=True);rawpath=rawdir/(key+'.npz');meta=rawdir/(key+'.json')
        if rawpath.exists():
            m=read(meta)
            if m['product_key']!=j['product_key']or file_hash(rawpath)!=m['sha256']:raise ValueError('Native archive changed')
        else:
            arrays=native(ee,j);tmp=rawpath.with_suffix('.pending.npz');np.savez_compressed(tmp,**arrays);os.replace(tmp,rawpath)
            write(meta,dict(product_key=j['product_key'],sha256=file_hash(rawpath),density_asset=j['density_asset'],landscan_asset=j['landscan_asset'],density_projection=plan['source_snapshot']['projections'][j['density_asset']],scope='Original raw source; NaNs/masks retained; not filled'))
        with np.load(rawpath)as z:raw={k:z[k]for k in z.files}
        geomdir=DATA/'overlaps';geomdir.mkdir(exist_ok=True);geom=geomdir/(j['grid_key']+'.npz')
        transform=plan['source_snapshot']['projections'][j['density_asset']]['transform']
        if geom.exists():
            geometry_record=read(geom.with_suffix('.json'))
            if file_hash(geom)!=geometry_record['sha256']:raise ValueError('Overlap cache checksum mismatch')
            with np.load(geom)as z:o={k:z[k]for k in z.files}
        else:
            o=build_overlaps(g,transform,raw['x'],raw['y']);tmp=geom.with_suffix('.pending.npz');np.savez_compressed(tmp,**o);os.replace(tmp,geom)
        # Shape and coordinate origin must be identical when reusing a grid's sparse map.
        sig=digest(dict(shape=list(raw['x'].shape),origin=[int(raw['x'][0,0]),int(raw['y'][0,0])],transform=transform))
        sigpath=geom.with_suffix('.json')
        if sigpath.exists()and read(sigpath)['native_lattice_signature']!=sig:raise ValueError('Native lattice changed across years')
        if not sigpath.exists():write(sigpath,dict(native_lattice_signature=sig,sha256=file_hash(geom),grid=g,software_sha256=plan['software_sha256']))
        data,qa=aggregate(raw,o,j['approved_missing_pixels']);p=DATA/'products'/j['group_id']/str(j['year']);p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():
            temp=Path(tempfile.mkdtemp(prefix='.pending-density-',dir=p.parent));tif=temp/'source.tif'
            with rasterio.open(tif,'w',driver='GTiff',height=g['rows'],width=g['cols'],count=4,dtype='float32',crs=g['crs'],transform=Affine(*j['crs_transform']),nodata=-9999,compress='deflate')as ds:
                ds.write(data.astype(np.float32))
                for band,name in enumerate(BANDS,1):ds.set_band_description(band,name)
                ds.update_tags(recipe=plan['recipe']['id'],epoch_role='split-independent candidate cache',aggregation_location='local physical polygon intersections of native GEE values')
            np.save(temp/'human_population_density.npy',data[0].astype(np.float32),allow_pickle=False)
            write(temp/'validation.json',dict(schema='validated_globpop_density_product/1',job_id=key,product_key=j['product_key'],grid=g,recipe=plan['recipe'],year=j['year'],
             raw_source_sha256=file_hash(rawpath),overlap_sha256=file_hash(geom),plan_sha256=file_hash(BUNDLE/'plan.json'),approval_sha256=plan['approval_sha256'],
             source_snapshot_fingerprint=plan['source_snapshot']['asset_fingerprint'],software_sha256=plan['software_sha256'],statistics=qa,
             epoch_role='shared split-independent candidate product',scientific_validation='not established; software QA only'))
            write(temp/'checksums.json',{f.name:file_hash(f)for f in temp.iterdir()});os.rename(temp,p)
        checks=read(p/'checksums.json')
        if any(file_hash(p/name)!=sha for name,sha in checks.items()):raise ValueError('Product checksum mismatch')
        # Give Drive each immutable product's unambiguous recipe/key filename.
        drivefile=DATA/'downloads'/(j['export_prefix']+'.tif');drivefile.parent.mkdir(exist_ok=True)
        if not drivefile.exists():
            import shutil
            shutil.copyfile(p/'source.tif',drivefile)
        if file_hash(drivefile)!=checks['source.tif']:raise ValueError('Drive staging file changed')
        remote=upload(drive,drivefile,config['drive_leaf_id'],DATA/'tasks'/(key+'.json'),j['product_key'])
        completed[key]=dict(group_id=j['group_id'],year=j['year'],product_key=j['product_key'],product=str(p),npy=str(p/'human_population_density.npy'),drive_file_id=remote['id'],statistics=qa)
        write(DATA/'acquisition.json',dict(schema='globpop_density_candidate_acquisition/1',status='COMPLETED'if len(completed)==24 else'PARTIAL',completed_jobs=len(completed),expected_jobs=24,group_count=13,
         groups=completed,plan_sha256=file_hash(BUNDLE/'plan.json'),driver_sha256=file_hash(__file__),transport='Native GEE sampleRectangle -> local physical overlap integration -> checksum-verified Drive TIFF',
         online_eecu_usage_seconds=None,online_eecu_usage_measured=False,scientific_validation='not established'))
        print(key,'validated',qa['native_fallback_pixels'],'native fallback pixels;',qa['fallback_cells'],'target cells; Drive checksum verified',flush=True)
    print('Completed',len(completed),'of24',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot-only',action='store_true');run(**vars(p.parse_args()))
