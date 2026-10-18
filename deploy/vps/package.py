"""Build a source-only VPS candidate from a clean tracked checkout; no raw data/secrets."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[2]

def allowed(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:return False
    if name in ('.dockerignore','OPEN_SOURCE_NOTICES.md'):return True
    if name.startswith('docs/licenses/'):return p.suffix=='.txt'
    if name.startswith('backend/'):
        if any(part in {'venv','.venv','__pycache__'} for part in p.parts):return False
        return (p.suffix=='.py' and not name.startswith('backend/tests/')) or (name.startswith('backend/infrastructure/migrations/') and p.suffix=='.sql') or name=='backend/requirements.lock'
    if name.startswith('frontend/integration/'):return p.suffix=='.js'
    if name.startswith('frontend/src/'):return p.suffix in {'.js','.jsx','.css','.png','.svg','.woff','.woff2','.ttf'}
    if name.startswith('frontend/public/licenses/'):return p.suffix=='.txt'
    if name in ('frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/vite.config.js','frontend/public/favicon.svg'):return True
    if name.startswith('deploy/vps/') and len(p.parts)==3:return p.name in {'__init__.py','settings.py','runtime.py','ops.py','preflight.py','package.py','Dockerfile.api','Dockerfile.web','Caddyfile','compose.yaml','.env.example','runtime.json.example','owner.json.example','README.md'}
    return name=='deploy/__init__.py'

def archive(root,files,target,commit,reader=None):
    selected=sorted(set(f for f in files if allowed(f)));manifest=dict(schemaVersion=1,sourceCommit=commit,classification='UNTESTED_CONTAINER_STAGING_CANDIDATE_NOT_SALES_ACCEPTANCE',files={})
    with Path(target).open('xb') as output:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in selected:
                path=root/name
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('SOURCE_PATH_REFUSED')
                raw=reader(name) if reader is not None else path.read_bytes();manifest['files'][name]=hashlib.sha256(raw).hexdigest()
                entry=zipfile.ZipInfo(name);entry.external_attr=0o100644<<16;entry.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(entry,raw)
            entry=zipfile.ZipInfo('RELEASE_MANIFEST.json');entry.external_attr=0o100644<<16;entry.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(entry,json.dumps(manifest,sort_keys=True,indent=2))
    return manifest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise ValueError('CLEAN_CHECKOUT_REQUIRED')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    files=subprocess.check_output(['git','ls-tree','-r','--name-only','-z',commit],cwd=ROOT).decode().split('\0')
    manifest=archive(ROOT,files,args.output,commit,reader=lambda name:subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT))
    sha=hashlib.sha256()
    with Path(args.output).open('rb') as stream:
        while block:=stream.read(1048576):sha.update(block)
    print(json.dumps(dict(sourceCommit=commit,files=len(manifest['files']),sha256=sha.hexdigest(),classification=manifest['classification'])))

if __name__=='__main__':main()
