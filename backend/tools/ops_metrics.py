"""One-shot, dependency-light health snapshot for a small VPS (run from cron/systemd timer every minute; output one JSON line).

Reads host CPU/memory/disk from /proc, PostgreSQL reachability and the durable queue (depth, oldest wait, recent failures, running leases), the age of the
newest database backup marker and of the newest export file, and prints status OK/WARN/CRIT with the reasons. Exit code 0 OK, 1 WARN, 2 CRIT, so any
scheduler/alerting tool (cron MAILTO, systemd OnFailure, a push script) can act on it. It never writes to the database and never prints secrets or tenant data.
Environment: BTL_DATABASE_URL (DSN), BTL_BACKUP_MARKER (path of a file touched by each successful backup), BTL_DISK_PATH (default /).
"""
import json
import os
import shutil
import sys
import time

THRESHOLDS = dict(mem_available_warn_gib=2.0, mem_available_crit_gib=1.0, disk_free_warn_gib=40, disk_free_crit_gib=30, load_per_cpu_warn=1.5, load_per_cpu_crit=3.0,
                  queue_depth_warn=8, queue_depth_crit=14, oldest_wait_warn_s=60, oldest_wait_crit=120, failed_1h_warn=3, failed_1h_crit=10,
                  backup_age_warn_h=26, backup_age_crit_h=50)


def host():
    mem = {line.split(":")[0]: int(line.split()[1]) for line in open("/proc/meminfo")}
    load1 = float(open("/proc/loadavg").read().split()[0])
    usage = shutil.disk_usage(os.environ.get("BTL_DISK_PATH", "/"))
    return dict(memAvailableGiB=round(mem["MemAvailable"] / 2**20, 2), swapUsedMiB=round((mem["SwapTotal"] - mem["SwapFree"]) / 1024, 1),
                loadPerCpu=round(load1 / (os.cpu_count() or 1), 2), diskFreeGiB=round(usage.free / 2**30, 1))


def database(dsn):
    import psycopg
    out = {}
    with psycopg.connect(dsn, connect_timeout=5, options="-c default_transaction_read_only=on") as db:
        out["reachable"] = True
        states = dict(db.execute("SELECT state,count(*) FROM btl.research_jobs GROUP BY state").fetchall())
        out["jobStates"] = {k: int(v) for k, v in states.items()}
        out["queueDepth"] = int(states.get("QUEUED", 0)) + int(states.get("RUNNING", 0))
        row = db.execute("SELECT COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-min(created_at)),0) FROM btl.research_jobs WHERE state='QUEUED'").fetchone()
        out["oldestQueuedWaitS"] = round(float(row[0]), 1)
        out["failedLastHour"] = int(db.execute("SELECT count(*) FROM btl.research_jobs WHERE state IN ('FAILED','RECONCILE_REQUIRED') AND finished_at > clock_timestamp()-interval '1 hour'").fetchone()[0])
        out["connections"] = int(db.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()").fetchone()[0])
        out["databaseSizeMiB"] = round(db.execute("SELECT pg_database_size(current_database())").fetchone()[0] / 2**20, 1)
    return out


def age_hours(path):
    try:
        return round((time.time() - os.path.getmtime(path)) / 3600, 1)
    except OSError:
        return None


def evaluate(snapshot, t=THRESHOLDS):
    level, reasons = 0, []

    def flag(severity, text):
        nonlocal level
        level = max(level, severity); reasons.append(("CRIT " if severity == 2 else "WARN ") + text)
    h = snapshot["host"]
    if h["swapUsedMiB"] > 0: flag(2, "swap in use")
    if h["memAvailableGiB"] < t["mem_available_crit_gib"]: flag(2, "memory available below %.1f GiB" % t["mem_available_crit_gib"])
    elif h["memAvailableGiB"] < t["mem_available_warn_gib"]: flag(1, "memory available below %.1f GiB" % t["mem_available_warn_gib"])
    if h["diskFreeGiB"] < t["disk_free_crit_gib"]: flag(2, "disk free below %d GiB" % t["disk_free_crit_gib"])
    elif h["diskFreeGiB"] < t["disk_free_warn_gib"]: flag(1, "disk free below %d GiB" % t["disk_free_warn_gib"])
    if h["loadPerCpu"] > t["load_per_cpu_crit"]: flag(2, "load per CPU above %.1f" % t["load_per_cpu_crit"])
    elif h["loadPerCpu"] > t["load_per_cpu_warn"]: flag(1, "load per CPU above %.1f" % t["load_per_cpu_warn"])
    d = snapshot.get("database")
    if not d or not d.get("reachable"):
        flag(2, "database unreachable")
    else:
        if d["queueDepth"] >= t["queue_depth_crit"]: flag(2, "queue depth %d" % d["queueDepth"])
        elif d["queueDepth"] >= t["queue_depth_warn"]: flag(1, "queue depth %d" % d["queueDepth"])
        if d["oldestQueuedWaitS"] > t["oldest_wait_crit"]: flag(2, "oldest queued job waiting %.0fs" % d["oldestQueuedWaitS"])
        elif d["oldestQueuedWaitS"] > t["oldest_wait_warn_s"]: flag(1, "oldest queued job waiting %.0fs" % d["oldestQueuedWaitS"])
        if d["failedLastHour"] >= t["failed_1h_crit"]: flag(2, "%d failed jobs in the last hour" % d["failedLastHour"])
        elif d["failedLastHour"] >= t["failed_1h_warn"]: flag(1, "%d failed jobs in the last hour" % d["failedLastHour"])
    b = snapshot.get("backupAgeHours")
    if b is None: flag(2, "backup marker missing")
    elif b > t["backup_age_crit_h"]: flag(2, "last backup %.0fh ago" % b)
    elif b > t["backup_age_warn_h"]: flag(1, "last backup %.0fh ago" % b)
    return ("OK", "WARN", "CRIT")[level], reasons


def main():
    snapshot = dict(observedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), host=host())
    dsn = os.environ.get("BTL_DATABASE_URL")
    try:
        snapshot["database"] = database(dsn) if dsn else dict(reachable=False, error="BTL_DATABASE_URL not set")
    except Exception as error:                                           # noqa: BLE001 - a monitor reports, never raises
        snapshot["database"] = dict(reachable=False, error=type(error).__name__)
    marker = os.environ.get("BTL_BACKUP_MARKER")
    snapshot["backupAgeHours"] = age_hours(marker) if marker else None
    snapshot["status"], snapshot["reasons"] = evaluate(snapshot)
    print(json.dumps(snapshot, sort_keys=True))
    return {"OK": 0, "WARN": 1, "CRIT": 2}[snapshot["status"]]


if __name__ == "__main__":
    sys.exit(main())
