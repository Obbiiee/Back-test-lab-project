"""Encrypted off-box backup of the product database (no cloud provider required).

Flow: pg_dump (custom format, via infrastructure.database.backup, which already hashes it) -> GnuPG PUBLIC-KEY encryption (the VPS holds only the public key; the
private key stays off the VPS) -> SHA-256 of the encrypted file -> upload with a command the owner configures (scp/sftp/rclone/anything) -> only after the upload
command succeeds, touch the marker file that tools/ops_metrics.py watches. Retention is applied to the remote by the owner's scheduler (7 daily, 4 weekly, 6 monthly).
Environment: BTL_DATABASE_URL, BTL_BACKUP_RECIPIENT (GnuPG key id/fingerprint), BTL_BACKUP_UPLOAD_CMD (with {file} and {sha} placeholders, run without a shell),
BTL_BACKUP_MARKER, BTL_BACKUP_WORKDIR (default /tmp), BTL_PG_BIN, GNUPGHOME optional. No secret is printed or written to the command line.
Restore (owner, off-box): gpg --decrypt file.gpg > product.dump; sha256sum -c; pg_restore into an EMPTY database (see infrastructure.database.restore).
"""
import hashlib
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_backup(env=os.environ):
    from infrastructure import database
    dsn, recipient, upload = env["BTL_DATABASE_URL"], env["BTL_BACKUP_RECIPIENT"], env["BTL_BACKUP_UPLOAD_CMD"]
    marker = env.get("BTL_BACKUP_MARKER")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    with tempfile.TemporaryDirectory(prefix="btl-backup-", dir=env.get("BTL_BACKUP_WORKDIR", "/tmp")) as tmp:
        dump = Path(tmp) / f"product-{stamp}.dump"
        dump_hash = database.backup(dsn, dump, env.get("BTL_PG_BIN", ""))
        encrypted = Path(str(dump) + ".gpg")
        subprocess.run(["gpg", "--batch", "--yes", "--trust-model", "always", "--recipient", recipient, "--output", str(encrypted), "--encrypt", str(dump)],
                       check=True, capture_output=True, timeout=600)
        dump.unlink()                                                   # the plaintext dump never outlives this step
        sha = hashlib.sha256(encrypted.read_bytes()).hexdigest()
        (Path(tmp) / (encrypted.name + ".sha256")).write_text(f"{sha}  {encrypted.name}\n")
        for artifact in (encrypted, Path(tmp) / (encrypted.name + ".sha256")):
            command = [part.replace("{file}", str(artifact)).replace("{sha}", sha) for part in shlex.split(upload)]
            subprocess.run(command, check=True, capture_output=True, timeout=1800)
        if marker:
            Path(marker).touch()                                        # only after every upload succeeded
        return dict(file=encrypted.name, sha256=sha, plaintextDumpHash=dump_hash)


if __name__ == "__main__":
    import json
    print(json.dumps(run_backup()))
