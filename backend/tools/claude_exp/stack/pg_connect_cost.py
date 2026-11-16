"""Micro-benchmark: PostgreSQL CPU cost of opening a connection per request vs reusing it (BTL_DB_POOL). QA only.
Starts a private disposable PostgreSQL (trust auth: NO password hashing cost, so production would cost MORE), runs N connect / SELECT 1 / close cycles
through infrastructure.database.connect(), and reads CPU of the postmaster including its reaped children (cutime/cstime = the short-lived backends)."""
import argparse, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
BACKEND = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(BACKEND))
PG_BIN = Path(os.environ.get('BTL_PG_BIN', Path.home() / 'tools' / 'pg17' / 'bin'))


def postmaster_cpu(pidfile):
    pid = int(open(pidfile).readline()); clk = os.sysconf('SC_CLK_TCK')
    f = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return (int(f[11]) + int(f[12]) + int(f[13]) + int(f[14])) / clk        # utime+stime+cutime+cstime


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--n', type=int, default=2000); ap.add_argument('--port', type=int, default=54433); ap.add_argument('--out')
    a = ap.parse_args(); work = Path(tempfile.mkdtemp(prefix='pgcost-')); env = dict(os.environ, PATH=f'{PG_BIN}:{os.environ["PATH"]}')
    subprocess.run([str(PG_BIN / 'initdb'), '-D', str(work / 'pg'), '-U', 'postgres', '--auth=trust', '-E', 'UTF8'], check=True, env=env, stdout=subprocess.DEVNULL)
    subprocess.run([str(PG_BIN / 'pg_ctl'), '-D', str(work / 'pg'), '-w', '-l', str(work / 'pg.log'), '-o', f'-p {a.port} -k {work} -c listen_addresses=127.0.0.1', 'start'], check=True, env=env, stdout=subprocess.DEVNULL)
    dsn = f'host=127.0.0.1 port={a.port} dbname=postgres user=postgres'; out = dict(n=a.n, auth='trust (no password hashing)')
    try:
        from infrastructure.database import connect
        from infrastructure import db_pool
        for label, pool in (('directConnectEveryTime', '0'), ('pooledReuse', '1')):
            os.environ['BTL_DB_POOL'] = pool; db_pool.SYNC.close_all()
            pidfile = work / 'pg' / 'postmaster.pid'
            c0, p0, w0 = postmaster_cpu(pidfile), time.process_time(), time.monotonic()
            for _ in range(a.n):
                with connect(dsn) as db:
                    db.execute('SELECT 1').fetchone()
            db_pool.SYNC.close_all(); time.sleep(0.5)
            c1, p1, w1 = postmaster_cpu(pidfile), time.process_time(), time.monotonic()
            out[label] = dict(pgCpuSeconds=round(c1 - c0, 3), pgCpuMsPerRequest=round(1000 * (c1 - c0) / a.n, 3), clientCpuMsPerRequest=round(1000 * (p1 - p0) / a.n, 3), wallMsPerRequest=round(1000 * (w1 - w0) / a.n, 3))
        out['sessionsOpened'] = None
    finally:
        subprocess.run([str(PG_BIN / 'pg_ctl'), '-D', str(work / 'pg'), '-m', 'fast', 'stop'], env=env, stdout=subprocess.DEVNULL)
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(out, indent=1))
    if a.out: Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
