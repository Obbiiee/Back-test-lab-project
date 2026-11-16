"""Pinned static-only staging update. No API/database/service/config operations."""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
import urllib.request
import zipfile


def require(ok, code):
    if not ok:
        raise ValueError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(raw, expected, commit, *, replace_home=False):
    require(len(raw) <= 64000000 and digest(raw) == expected, 'ARCHIVE_CHANGED')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) < 200 and len({i.filename for i in infos}) == len(infos), 'ARCHIVE_MEMBERS')
        require(all(not i.is_dir() and i.file_size <= 16000000 and not stat.S_ISLNK(i.external_attr >> 16)
                    for i in infos) and sum(i.file_size for i in infos) <= 64000000, 'ARCHIVE_SIZE_TYPE')
        manifest = json.loads(archive.read('manifest.json'))
        require(set(manifest) == {'sourceCommit', 'mode', 'files'} and manifest['sourceCommit'] == commit
                and manifest['mode'] == 'STAGING_UI_NOT_VISUAL_ACCEPTANCE', 'MANIFEST')
        files = manifest['files']
        require(type(files) is dict and 'login/index.html' in files
                and set(files) | {'manifest.json'} == {i.filename for i in infos}, 'MANIFEST_FILES')
        result = {}
        for name, sha in files.items():
            require(name == 'login/index.html' or (replace_home and name == 'index.html') or re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(js|css|png|woff2)', name), 'PATH')
            content = archive.read(name)
            require(type(sha) is str and digest(content) == sha, 'FILE_HASH')
            result[name] = content
        require(b'<html' in result['login/index.html'].lower(), 'LOGIN_HTML')
        if 'index.html' in result:
            require(b'<html' in result['index.html'].lower(), 'HOME_HTML')
        for name, content in result.items():
            if name.endswith('.html'):
                references = re.findall(rb'(?:src|href)="(/assets/[^"]+)"', content)
                require(all(ref.decode('ascii').lstrip('/') in result for ref in references), 'MISSING_HTML_ASSET')
        return result


def prepare(old, destination, files, *, replace_home=False):
    require(old.is_dir() and not old.is_symlink() and not destination.exists(), 'RELEASE_PATH')
    for p in old.rglob('*'):
        require(not p.is_symlink() and (p.is_dir() or p.is_file()), 'OLD_RELEASE_TYPE')
    landing = files['index.html'] if replace_home and 'index.html' in files else (old/'index.html').read_bytes()
    require('index.html' not in files or replace_home, 'HOME_REPLACEMENT_NOT_AUTHORIZED')
    shutil.copytree(old, destination)
    try:
        for name, raw in files.items():
            path = destination/name
            if name.startswith('assets/') and path.exists():
                require(path.read_bytes() == raw, 'ASSET_COLLISION')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o644)
        for path in [destination, *destination.rglob('*')]:
            if path.is_dir():
                path.chmod(0o755)
        require((destination/'index.html').read_bytes() == landing, 'LANDING_CHANGED')
    except Exception:
        shutil.rmtree(destination)
        raise


def switch(link, target, expected):
    require(link.is_symlink() and link.resolve() == expected, 'LIVE_VERSION_DRIFT')
    temporary = link.with_name('.current-static-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def verify_switch(link, new, old, expected, fetch):
    switch(link, new, old)
    try:
        require(fetch() == expected, 'PUBLIC_LOGIN_HASH')
    except Exception:
        switch(link, old, new)
        raise


def public_login():
    request = urllib.request.Request('https://riksora.com/login/', headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        require(response.status == 200 and response.url == 'https://riksora.com/login/', 'PUBLIC_LOGIN_STATUS')
        return response.read(1000000)


def public_release(files):
    for name, expected in files.items():
        path = '/' if name == 'index.html' else '/login/' if name == 'login/index.html' else '/' + name
        request = urllib.request.Request('https://riksora.com' + path, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=20) as response:
            require(response.status == 200 and response.url == 'https://riksora.com' + path,
                    'PUBLIC_FILE_STATUS')
            require(response.read(len(expected) + 1) == expected, 'PUBLIC_FILE_HASH')
    return True


def read_pinned(path, expected):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'ARCHIVE_TYPE')
        raw = stream.read(64000001)
    require(len(raw) <= 64000000 and digest(raw) == expected, 'ARCHIVE_CHANGED')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive'); parser.add_argument('--sha'); parser.add_argument('--commit')
    parser.add_argument('--expected-release'); parser.add_argument('--rollback')
    parser.add_argument('--replace-home', action='store_true', help='Explicitly replace landing with manifest-pinned repository home')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'OPERATOR_SUDO_REQUIRED')
    os.umask(0o077)
    with open('/run/riksora-demo-upgrade.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        link = Path('/srv/riksora/current')
        releases = Path('/srv/riksora/releases')
        if args.rollback:
            snapshot = Path(args.rollback)
            require(snapshot.parent == Path('/var/backups/riksora-beta') and snapshot.name.startswith('static-')
                    and snapshot.is_dir() and not snapshot.is_symlink() and snapshot.stat().st_uid == 0,
                    'ROLLBACK_PATH')
            state = json.loads((snapshot/'state.json').read_text())
            old, new = Path(state['old']), Path(state['new'])
            require(old.parent == releases and new.parent == releases and old.is_dir() and new.is_dir(), 'ROLLBACK_TARGET')
            switch(link, old, new)
            print('STATIC_ROLLBACK_APPLIED; DATABASE_AND_SERVICES_UNCHANGED')
            return
        require(args.commit and re.fullmatch('[0-9a-f]{40}', args.commit), 'COMMIT')
        old = Path(args.expected_release or '')
        require(old.parent == releases and old.is_dir() and not old.is_symlink()
                and old.stat().st_uid == 0 and not old.stat().st_mode & 0o022, 'OLD_RELEASE')
        require(link.is_symlink() and link.resolve() == old, 'LIVE_VERSION_DRIFT')
        for path in [old, *old.rglob('*')]:
            require(not path.is_symlink() and path.stat().st_uid == 0
                    and not path.stat().st_mode & 0o022, 'OLD_RELEASE_OWNERSHIP')
        files = validate(read_pinned(args.archive, args.sha), args.sha, args.commit, replace_home=args.replace_home)
        new = releases/(args.commit[:12] + '-claude-ui')
        snapshot = Path(tempfile.mkdtemp(prefix='static-', dir='/var/backups/riksora-beta'))
        (snapshot/'state.json').write_text(json.dumps({'old': str(old), 'new': str(new), 'commit': args.commit,
                                                     'archiveSha256': args.sha}, sort_keys=True))
        (snapshot/'installer.py').write_bytes(Path(__file__).read_bytes())
        prepare(old, new, files, replace_home=args.replace_home)
        verify_switch(link, new, old, True, lambda: public_release(files))
        print('STATIC_UI_APPLIED; DATABASE_API_AND_CADDY_UNCHANGED' if args.replace_home else 'STATIC_UI_APPLIED; DATABASE_API_CADDY_AND_LANDING_UNCHANGED')
        print('Rollback snapshot: ' + str(snapshot))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) else type(error).__name__
        print('STATIC_UPGRADE_REFUSED:' + code)
        raise SystemExit(1) from None
