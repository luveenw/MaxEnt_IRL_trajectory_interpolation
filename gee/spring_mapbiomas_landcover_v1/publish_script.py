"""Publish only this verified extraction script; OAuth headers remain in memory."""
from pathlib import Path
import os,subprocess,hashlib,json
import ee
from google.auth.transport.requests import Request
from jaguar_irl.training.shared_storage import write
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
script=(HERE/'jobs/extract_landcover.js').read_bytes()
repo_url='https://earthengine.googlesource.com/users/luveenw/ColumbiaMAThesis'
clone=Path('/tmp/codex-mapbiomas-gee-script-repo')
c=ee.data.get_persistent_credentials();c.refresh(Request())
env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='http.extraHeader',GIT_CONFIG_VALUE_0='Authorization: Bearer '+c.token)
def git(args):
    p=subprocess.run(['git']+args,env=env,text=True,capture_output=True)
    if p.returncode:raise RuntimeError('Git operation failed: '+p.stderr)
    return p.stdout.strip()
if not clone.exists():git(['clone',repo_url,str(clone)])
else:git(['-C',str(clone),'pull','--ff-only'])
relative='seasonal_covariates/pantanal_spring_mapbiomas_landcover_v1/extract_landcover'
target=clone/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(script)
git(['-C',str(clone),'add','--',relative])
if git(['-C',str(clone),'diff','--cached','--name-only']):
    git(['-C',str(clone),'-c','user.name=Codex','-c','user.email=codex@openai.com','commit','-m','Add Spring MapBiomas grassland and wetland candidate cache'])
    # A concurrent ESA publication must be preserved; rebase only this new commit.
    git(['-C',str(clone),'pull','--rebase'])
    git(['-C',str(clone),'push','origin','HEAD:master'])
commit=git(['-C',str(clone),'rev-parse','HEAD'])
git(['-C',str(clone),'fetch','origin','master'])
content=subprocess.run(['git','-C',str(clone),'show','origin/master:'+relative],env=env,capture_output=True,check=True).stdout
assert content==script
url='https://code.earthengine.google.com/?scriptPath=users%2Fluveenw%2FColumbiaMAThesis%3Aseasonal_covariates%2Fpantanal_spring_mapbiomas_landcover_v1%2Fextract_landcover'
record=dict(schema='earth_engine_script_publication/1',repository='users/luveenw/ColumbiaMAThesis',repository_url=repo_url,branch='master',commit=commit,script_path=relative,script_sha256=hashlib.sha256(script).hexdigest(),remote_content_hash_verified=True,code_editor_url=url,local_script=str(HERE/'jobs/extract_landcover.js'),scope='script publication; execution tracked separately')
write(DATA/'publication.json',record)
print(json.dumps(record,indent=2))
