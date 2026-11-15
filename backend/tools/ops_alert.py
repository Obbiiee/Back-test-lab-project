"""Light alerting around tools/ops_metrics.py: run it, and when the status is WARN/CRIT call the owner's command (mail, curl to a push service, anything) with the
message. Repeats of the same status are suppressed for BTL_ALERT_REPEAT_S (default 3600 s) via a small state file; a worse status or a recovery notifies at once.
The command is run without a shell; {message} is substituted. No credential is stored here: the command line or the program it calls reads its own secret file."""
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def decide(status, previous, now, repeat_s):
    """Returns the notification kind or None. previous = {'status':..., 'at': epoch} or None."""
    prev_status = (previous or {}).get("status", "OK")
    if status == "OK":
        return "RECOVERED" if prev_status != "OK" else None
    if prev_status == "OK" or (status == "CRIT" and prev_status != "CRIT"):
        return status
    return status if now - previous.get("at", 0) >= repeat_s else None


def main(env=os.environ, snapshot=None):
    from tools import ops_metrics
    state_path = Path(env.get("BTL_ALERT_STATE", "/tmp/btl-alert-state.json"))
    snap = snapshot
    if snap is None:
        host = ops_metrics.host()
        snap = dict(host=host, database=None, backupAgeHours=None)
        try:
            snap["database"] = ops_metrics.database(env["BTL_DATABASE_URL"]) if env.get("BTL_DATABASE_URL") else dict(reachable=False)
        except Exception:                                              # noqa: BLE001
            snap["database"] = dict(reachable=False)
        marker = env.get("BTL_BACKUP_MARKER")
        snap["backupAgeHours"] = ops_metrics.age_hours(marker) if marker else None
    status, reasons = ops_metrics.evaluate(snap)
    try:
        previous = json.loads(state_path.read_text())
    except (OSError, ValueError):
        previous = None
    now = time.time()
    kind = decide(status, previous, now, int(env.get("BTL_ALERT_REPEAT_S", "3600")))
    if kind and env.get("BTL_ALERT_CMD"):
        message = f"RIKSORA {kind}: " + ("; ".join(reasons) if reasons else "all checks OK")
        subprocess.run([part.replace("{message}", message) for part in shlex.split(env["BTL_ALERT_CMD"])], check=False, capture_output=True, timeout=60)
    if kind or previous is None or previous.get("status") != status:
        state_path.write_text(json.dumps(dict(status=status, at=now)))
    return kind, status, reasons


if __name__ == "__main__":
    kind, status, reasons = main()
    print(json.dumps(dict(status=status, notified=kind, reasons=reasons)))
    sys.exit({"OK": 0, "WARN": 1, "CRIT": 2}[status])
