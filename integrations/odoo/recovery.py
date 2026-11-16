"""Explicit cold business backup; trusted-hash recovery into a different empty DB only."""
import argparse,hashlib,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
from infrastructure.database import connect,_libpq_env

MAX_BYTES=2147483648
MAX_FILES=100000

def need(ok):
    if not ok:raise ValueError('ODOO_RECOVERY_REFUSED')
def fingerprint(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data:=stream.read(1048576):sha.update(data)
    return sha.hexdigest()
def command(dsn,bin_directory,name,args):
    # Credentials are libpq environment only, never argv or printed errors.
    subprocess.run([str(Path(bin_directory)/name),*args],env=_libpq_env(dsn),check=True,capture_output=True,timeout=180)
def database(dsn,*,empty=False):
    with connect(dsn) as db:
        db.execute('SET TRANSACTION READ ONLY')
        name=db.execute('SELECT current_database()').fetchone()[0]
        need(db.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'").fetchone()[0]==0)
        if empty:need(db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'").fetchone()[0]==0)
        return name

def checked(path,expected_hash):
    need(type(expected_hash) is str and re.fullmatch('[0-9a-f]{64}',expected_hash) and fingerprint(path)==expected_hash)
    with zipfile.ZipFile(path) as bundle:
        entries=bundle.infolist();names=[x.filename for x in entries]
        need(len(entries)<=MAX_FILES+2 and len(set(names))==len(names) and sum(x.file_size for x in entries)<=MAX_BYTES)
        need('MANIFEST.json' in names and 'database.dump' in names)
        info=bundle.getinfo('MANIFEST.json');need(info.file_size<=16777216)
        manifest=json.loads(bundle.read(info))
        need(type(manifest) is dict and set(manifest)=={'format','database','odooSourceCommit','files'} and manifest['format']=='BTL-ODOO-COLD-BACKUP-1')
        need(type(manifest['database']) is str and re.fullmatch('[A-Za-z0-9_-]{1,63}',manifest['database']))
        need(type(manifest['odooSourceCommit']) is str and re.fullmatch('[0-9a-f]{40}',manifest['odooSourceCommit']))
        need(type(manifest['files']) is dict and set(manifest['files'])==set(names)-{'MANIFEST.json'})
        for entry in entries:
            name=entry.filename;p=PurePosixPath(name)
            need(not entry.is_dir() and not p.is_absolute() and '..' not in p.parts and '\\' not in name and (entry.external_attr>>16)&0o170000!=0o120000)
            need(name in ('database.dump','MANIFEST.json') or len(p.parts)==3 and p.parts[0]=='filestore' and re.fullmatch('[0-9a-f]{2}',p.parts[1]) and re.fullmatch('[0-9a-f]{40}',p.parts[2]) and p.parts[2].startswith(p.parts[1]))
            if name=='MANIFEST.json':continue
            expected=manifest['files'][name];need(type(expected) is dict and set(expected)=={'sha256','bytes'} and type(expected['bytes']) is int and expected['bytes']==entry.file_size)
            sha=hashlib.sha256();content=hashlib.sha1()
            with bundle.open(entry) as stream:
                while data:=stream.read(1048576):sha.update(data);content.update(data)
            need(sha.hexdigest()==expected['sha256'])
            if name.startswith('filestore/'):need(content.hexdigest()==p.name)
    return manifest

def backup(dsn,filestore,target,bin_directory,odoo_commit,*,quiesced=False):
    need(quiesced is True and re.fullmatch('[0-9a-f]{40}',odoo_commit))
    source=Path(filestore);need(source.is_dir() and not source.is_symlink() and not source.is_junction())
    need(not Path(target).resolve().is_relative_to(source.resolve()))
    name=database(dsn);need(source.name==name and re.fullmatch('[A-Za-z0-9_-]{1,63}',name))
    files=[]
    for item in source.rglob('*'):
        need(not item.is_symlink() and not item.is_junction() and item.resolve().is_relative_to(source.resolve()))
        if item.is_file():
            rel=item.relative_to(source).as_posix()
            # GC checklist markers are not attachment bytes; do not restore them.
            if rel.startswith('checklist/'):continue
            need(re.fullmatch('[0-9a-f]{2}/[0-9a-f]{40}',rel) and rel[3:].startswith(rel[:2]));files.append((item,'filestore/'+rel))
    need(len(files)<=MAX_FILES and sum(x.stat().st_size for x,_ in files)<=MAX_BYTES)
    with connect(dsn) as db:
        db.execute('SET TRANSACTION READ ONLY')
        references=db.execute('SELECT store_fname,file_size,checksum FROM ir_attachment WHERE store_fname IS NOT NULL ORDER BY id LIMIT 100001').fetchall()
    need(len(references)<=MAX_FILES)
    present={entry.removeprefix('filestore/'):item for item,entry in files}
    for rel,size,checksum in references:
        need(type(rel) is str and rel in present and type(size) is int and size>=0 and present[rel].stat().st_size==size and rel.split('/')[-1]==checksum)

    with tempfile.TemporaryDirectory(prefix='btl-odoo-cold-') as temporary:
        dump=Path(temporary)/'database.dump';command(dsn,bin_directory,'pg_dump',['--format=custom','--no-owner','--no-acl','--file',str(dump)])
        files.insert(0,(dump,'database.dump'));need(sum(x.stat().st_size for x,_ in files)<=MAX_BYTES)
        manifest=dict(format='BTL-ODOO-COLD-BACKUP-1',database=name,odooSourceCommit=odoo_commit,files={})
        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as output:
            with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as bundle:
                for item,entry in files:
                    sha=hashlib.sha256();content=hashlib.sha1();size=0
                    with item.open('rb') as stream,bundle.open(entry,'w',force_zip64=True) as dest:
                        while data:=stream.read(1048576):size+=len(data);sha.update(data);content.update(data);dest.write(data)
                    if entry.startswith('filestore/'):need(content.hexdigest()==PurePosixPath(entry).name)
                    manifest['files'][entry]=dict(sha256=sha.hexdigest(),bytes=size)
                bundle.writestr('MANIFEST.json',json.dumps(manifest,sort_keys=True,separators=(',',':')))
    sha=fingerprint(target);checked(target,sha)
    return dict(sha256=sha,files=len(manifest['files']),format=manifest['format'])

def restore(dsn,filestore,archive,expected_hash,bin_directory,*,quiesced=False):
    need(quiesced is True);manifest=checked(archive,expected_hash)
    name=database(dsn,empty=True);target=Path(filestore)
    need(name!=manifest['database'] and target.name==name and not target.exists() and target.parent.is_dir())
    # Never overwrite or delete a source/target. A failure leaves a rejected partial
    # target for operator review; use another empty destination for another attempt.
    target.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='btl-odoo-restore-') as temporary,zipfile.ZipFile(archive) as bundle:
        dump=Path(temporary)/'database.dump'
        for entry in manifest['files']:
            path=dump if entry=='database.dump' else target.joinpath(*PurePosixPath(entry).parts[1:])
            need(path==dump or path.resolve().is_relative_to(target.resolve()));path.parent.mkdir(parents=True,exist_ok=True)
            with bundle.open(entry) as source,path.open('xb') as dest:
                while data:=source.read(1048576):dest.write(data)
        command(dsn,bin_directory,'pg_restore',['--dbname',name,'--single-transaction','--exit-on-error','--no-owner','--no-acl',str(dump)])
    return dict(restored=True,files=len(manifest['files']),format=manifest['format'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['backup','restore']);parser.add_argument('--filestore',required=True);parser.add_argument('--archive',required=True);parser.add_argument('--hash');parser.add_argument('--odoo-commit');parser.add_argument('--quiesced',action='store_true');args=parser.parse_args()
    try:
        dsn=os.environ['BTL_ODOO_RECOVERY_DSN'];bin_directory=os.environ['BTL_PG_BIN']
        result=backup(dsn,args.filestore,args.archive,bin_directory,args.odoo_commit or '',quiesced=args.quiesced) if args.operation=='backup' else restore(dsn,args.filestore,args.archive,args.hash,bin_directory,quiesced=args.quiesced)
    except Exception:print('ODOO_RECOVERY_FAILED_REVIEW_PRIVATE_TARGET');return 1
    print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
