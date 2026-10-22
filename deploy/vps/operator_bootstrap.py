"""Freeze a pinned operator plan/source archive before importing upgrade code.

Invoke via the isolated installed Python (-I), with this file's hash checked by
the short operator launcher. No home/PYTHONPATH modules are imported as root.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import stat
import sys
import tempfile
import zipfile


def read_regular(path, maximum):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('REGULAR_INPUT_REQUIRED')
        raw=stream.read(maximum+1)
    if len(raw)>maximum:
        raise ValueError('INPUT_SIZE')
    return raw


def stage(plan_path, expected_plan_hash, parent):
    raw=read_regular(plan_path,131072)
    if hashlib.sha256(raw).hexdigest()!=expected_plan_hash:
        raise ValueError('PLAN_CHANGED')
    plan=json.loads(raw)
    data=read_regular(plan['archive'],100000000)
    if hashlib.sha256(data).hexdigest()!=plan['archiveHash']:
        raise ValueError('ARCHIVE_CHANGED')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or len(names)>2000:
            raise ValueError('ARCHIVE_DIRECTORY')
        if archive.getinfo('RELEASE_MANIFEST.json').file_size>1048576:
            raise ValueError('ARCHIVE_MANIFEST_SIZE')
        manifest=json.loads(archive.read('RELEASE_MANIFEST.json'))
        if set(names)!=set(manifest['files'])|{'RELEASE_MANIFEST.json'}:
            raise ValueError('ARCHIVE_FILE_SET')
        if manifest['sourceCommit']!=plan['sourceCommit']:
            raise ValueError('COMMIT_CHANGED')
        total=0
        contents={}
        for name,expected in manifest['files'].items():
            path=PurePosixPath(name)
            item=archive.getinfo(name)
            total+=item.file_size
            if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in name:
                raise ValueError('ARCHIVE_PATH')
            if stat.S_IFMT(item.external_attr>>16) not in (0,stat.S_IFREG):
                raise ValueError('ARCHIVE_LINK')
            if item.file_size>25000000 or total>100000000:
                raise ValueError('ARCHIVE_SIZE')
            content=archive.read(name)
            if hashlib.sha256(content).hexdigest()!=expected:
                raise ValueError('ARCHIVE_FILE_HASH')
            contents[name]=content
    required={'deploy/__init__.py','deploy/vps/__init__.py','deploy/vps/package.py',
              'deploy/vps/native_demo_upgrade.py','deploy/vps/google_staging.py'}
    if not required<=set(contents):
        raise ValueError('BOOTSTRAP_SOURCE_MISSING')
    directory=Path(tempfile.mkdtemp(prefix='operator-bootstrap-',dir=parent))
    directory.chmod(0o700)
    source=directory/'source';source.mkdir(mode=0o700)
    for name,content in contents.items():
        target=source/name
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o600)
    (directory/'source.zip').write_bytes(data)
    (directory/'source.zip').chmod(0o600)
    plan={**plan,'archive':str(directory/'source.zip')}
    (directory/'plan.json').write_text(json.dumps(plan,indent=2))
    (directory/'plan.json').chmod(0o600)
    return directory,source


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True)
    parser.add_argument('--plan-hash',required=True)
    args=parser.parse_args()
    try:
        if os.geteuid()!=0 or not sys.flags.isolated:
            raise ValueError('ISOLATED_OPERATOR_PYTHON_REQUIRED')
        os.umask(0o077)
        directory,source=stage(args.plan,args.plan_hash,Path('/var/backups/riksora-beta'))
        sys.path[:0]=[str(source),str(source/'backend')]
        sys.argv=[str(source/'deploy/vps/native_demo_upgrade.py'),'--apply-plan',str(directory/'plan.json')]
        runpy.run_path(sys.argv[0],run_name='__main__')
    except Exception as error:
        print('OPERATOR_BOOTSTRAP_REFUSED:'+type(error).__name__,file=sys.stderr)
        raise SystemExit(1) from None
