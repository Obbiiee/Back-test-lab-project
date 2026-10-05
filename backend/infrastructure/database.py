"""Explicit PostgreSQL lifecycle operations; never automatic on API startup."""
import argparse
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql
from contracts.primitives import require
from .codec import fingerprint

MIGRATIONS = Path(__file__).with_name("migrations")


def _libpq_env(dsn):
    names = {"host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT", "dbname": "PGDATABASE",
             "user": "PGUSER", "password": "PGPASSWORD", "sslmode": "PGSSLMODE", "sslcert": "PGSSLCERT",
             "sslkey": "PGSSLKEY", "sslrootcert": "PGSSLROOTCERT", "sslcrl": "PGSSLCRL",
             "connect_timeout": "PGCONNECT_TIMEOUT", "application_name": "PGAPPNAME", "options": "PGOPTIONS",
             "service": "PGSERVICE", "target_session_attrs": "PGTARGETSESSIONATTRS", "channel_binding": "PGCHANNELBINDING"}
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    require(set(info).issubset(names), "backupConnectionOptions")
    return {**{key: value for key, value in os.environ.items() if not key.startswith("PG")},
            **{names[key]: value for key, value in info.items()}}


def connect(dsn):
    # Caller config owns TLS and credentials. Bound connect/lock/query waits.
    return psycopg.connect(dsn, connect_timeout=5, options="-c statement_timeout=15000 -c lock_timeout=10000")


def migrate(dsn, directory=MIGRATIONS):
    with connect(dsn) as db:
        db.execute("SELECT pg_advisory_xact_lock(2020, 1)")
        db.execute("CREATE TABLE IF NOT EXISTS public.btl_migrations (version text PRIMARY KEY, checksum text NOT NULL)")
        recorded = dict(db.execute("SELECT version, checksum FROM public.btl_migrations").fetchall())
        files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
        require(set(recorded).issubset({p.name for p in files}), "migrationVersion", "MIGRATION_DRIFT")
        for path in files:
            # Normalize checkout line endings; Git on Windows may use CRLF.
            raw = path.read_text(encoding="utf-8").encode("utf-8")
            checksum = fingerprint(raw)
            if path.name in recorded:
                require(recorded[path.name] == checksum, "migrationChecksum", "MIGRATION_DRIFT")
                continue
            db.execute(raw.decode("utf-8"))
            db.execute("INSERT INTO public.btl_migrations VALUES (%s,%s)", (path.name, checksum))


def grant_runtime(dsn, role):
    """Operator supplies an existing non-owner role; no passwords/roles invented."""
    with connect(dsn) as db:
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA btl TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT SELECT,INSERT ON btl.session_contexts,btl.command_reviews,btl.intakes,btl.evidence,btl.passports,btl.lineage TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT UPDATE ON btl.session_contexts TO {}").format(sql.Identifier(role)))


def backup(dsn, target, bin_directory=""):
    target = Path(target)
    require(not target.exists(), "backupTarget")
    # No credentials on process command lines. libpq reads connection via env.
    env = _libpq_env(dsn)
    executable = str(Path(bin_directory) / "pg_dump") if bin_directory else "pg_dump"
    subprocess.run([executable, "--format=custom", "--no-owner", "--no-acl", "--file", str(target)],
                   env=env, check=True, capture_output=True, timeout=120)
    return fingerprint(target.read_bytes())


def restore(dsn, source, expected_hash, bin_directory=""):
    source = Path(source)
    require(fingerprint(source.read_bytes()) == expected_hash, "backupHash", "CORRUPT_RECORD")
    with connect(dsn) as db:
        count = db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'").fetchone()[0]
        count += db.execute("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%'").fetchone()[0]
        count += db.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%'").fetchone()[0]
        require(count == 0, "restoreTarget", "NONEMPTY_RESTORE_TARGET")
    executable = str(Path(bin_directory) / "pg_restore") if bin_directory else "pg_restore"
    env = _libpq_env(dsn)
    subprocess.run([executable, "--dbname", env["PGDATABASE"], "--no-owner", "--no-acl", "--single-transaction", str(source)],
                   env=env, check=True, capture_output=True, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["migrate", "backup", "restore"])
    parser.add_argument("--file")
    parser.add_argument("--hash")
    parser.add_argument("--runtime-role")
    args = parser.parse_args()
    dsn = os.environ["BTL_DATABASE_URL"]
    if args.operation == "migrate":
        migrate(dsn)
        if args.runtime_role:
            grant_runtime(dsn, args.runtime_role)
    elif args.operation == "backup":
        print(backup(dsn, args.file, os.getenv("BTL_PG_BIN", "")))
    else:
        restore(dsn, args.file, args.hash, os.getenv("BTL_PG_BIN", ""))


if __name__ == "__main__":
    main()
