#!/bin/bash
# Backup of the public application database (custom-format pg_dump, 0600, outside the repository) and an OPTIONAL restore drill into a throw-away cluster.
#   backup_accounts.sh backup           -> ~/backups/prod-btl-<UTC stamp>.dump (+ .sha256), verified with pg_restore --list
#   backup_accounts.sh drill [dump]     -> restores into a disposable cluster on 127.0.0.1:54471 and compares row counts with the live database; destroys the drill cluster
# Never writes to the live database; credentials come from ~/.config/riksora-db.env and are never printed.
set -euo pipefail
PGBIN="$HOME/tools/pg17/bin"; export PATH="$PGBIN:$PATH"
set -a; . "$HOME/.config/riksora-db.env"; set +a
OUT="$HOME/backups"; mkdir -p "$OUT"; chmod 700 "$OUT"
LIVE="host=127.0.0.1 port=54450 dbname=btl user=postgres"
TABLES="users workspaces memberships tick_sessions tick_commands tick_events tick_checkpoints research_jobs entitlement_claims auth_sessions"
counts() { for t in $TABLES; do printf "%s=%s " "$t" "$(PGPASSWORD="$2" psql -h 127.0.0.1 -p "$1" -U postgres -d btl -Atc "select count(*) from btl.$t" 2>/dev/null || echo NA)"; done; echo; }
case "${1:-}" in
  backup)
    STAMP=$(date -u +%Y%m%dT%H%M%SZ); F="$OUT/prod-btl-$STAMP.dump"
    PGPASSWORD="$PG_SUPER_PASSWORD" pg_dump -h 127.0.0.1 -p 54450 -U postgres -d btl -Fc -f "$F"
    chmod 600 "$F"; pg_restore --list "$F" > /dev/null          # the archive must be readable end to end
    sha256sum "$F" | cut -d' ' -f1 > "$F.sha256"; chmod 600 "$F.sha256"
    echo "BACKUP_OK $F $(stat -c %s "$F") bytes sha256=$(cat "$F.sha256")"
    ;;
  drill)
    F="${2:-$(ls -1t "$OUT"/prod-btl-*.dump | head -1)}"; [ -f "$F" ] || { echo "no dump"; exit 2; }
    [ "$(sha256sum "$F" | cut -d' ' -f1)" = "$(cat "$F.sha256")" ] || { echo "CHECKSUM_MISMATCH"; exit 3; }
    D=$(mktemp -d "$OUT/drill-XXXXXX"); mkdir -p "$D/sock"
    initdb -D "$D/pg" -U postgres --auth=trust -E UTF8 > /dev/null
    printf "port=54471\nlisten_addresses='127.0.0.1'\nunix_socket_directories='$D/sock'\n" >> "$D/pg/postgresql.conf"
    pg_ctl -D "$D/pg" -w -l "$D/pg.log" start > /dev/null
    trap 'pg_ctl -D "$D/pg" -m immediate -w stop >/dev/null 2>&1 || true; rm -rf "$D"' EXIT
    psql -h 127.0.0.1 -p 54471 -U postgres -qc "create role btl_owner login" -c "create role btl_app login" -c "create database btl owner btl_owner" > /dev/null
    pg_restore -h 127.0.0.1 -p 54471 -U postgres -d btl --no-owner "$F" > "$D/restore.log" 2>&1 || true
    LIVE_C=$(counts 54450 "$PG_SUPER_PASSWORD"); DRILL_C=$(counts 54471 "x")
    echo "live : $LIVE_C"; echo "drill: $DRILL_C"
    [ "$LIVE_C" = "$DRILL_C" ] && echo "DRILL_OK row counts identical" || { echo "DRILL_DIFFERS (live changed after the dump, or restore incomplete)"; exit 4; }
    ;;
  *) echo "usage: $0 backup | drill [dump]"; exit 1;;
esac
