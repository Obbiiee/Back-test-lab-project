#!/bin/bash
# Daily backup of the public application database: one verified dump (backup_accounts.sh backup), then keep only the newest KEEP dumps.
# Only files named prod-btl-*.dump(+.sha256) in ~/backups are ever pruned. Runs from the riksora-backup.timer systemd user timer.
set -euo pipefail
KEEP="${KEEP:-14}"; DIR="$HOME/backups"
"$(dirname "$0")/backup_accounts.sh" backup
ls -1t "$DIR"/prod-btl-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do rm -f -- "$old" "$old.sha256"; echo "pruned $(basename "$old")"; done
echo "BACKUP_DAILY_OK kept=$(ls -1 "$DIR"/prod-btl-*.dump | wc -l)"
