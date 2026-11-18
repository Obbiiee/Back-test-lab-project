#!/bin/bash
# Promotion of checkpoint V2 (BTL_TICK_CHECKPOINT_FORMAT=compact-v2) on the public application, with gates, backup, smoke test and automatic rollback.
#   v2_promote.sh status      read-only: flag state, memory, database size, job states, recent failures
#   v2_promote.sh check       read-only: every deployment gate (service state, disk, memory, swap, idle queue, fresh verified backup)
#   v2_promote.sh apply       REFUSES unless RIKSORA_V2_APPROVED=YES-<today UTC date> is set by the owner. Backup -> add the flag -> restart -> smoke --expect v2 ->
#                             on any failure: remove the flag, restart, smoke --expect v1, exit 1
#   v2_promote.sh rollback    remove the flag, restart, smoke --expect v1
# RIKSORA_DRY_RUN=1 prints what apply/rollback would do and changes nothing. Secrets are never printed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ENVF="$HOME/prod/app.env"; FLAG='BTL_TICK_CHECKPOINT_FORMAT=compact-v2'
PY="$HOME/tools/venv313/bin/python"; export PATH="$HOME/tools/pg17/bin:$PATH"
set -a; . "$HOME/.config/riksora-db.env"; set +a
say() { printf '%s\n' "$*"; }
dry() { [ "${RIKSORA_DRY_RUN:-0}" = "1" ]; }
flag_on() { grep -qx "$FLAG" "$ENVF"; }
runtime_on() { P=$(systemctl --user show -p MainPID --value riksora-api); tr '\0' '\n' < /proc/$P/environ 2>/dev/null | grep -qx "$FLAG"; }
q() { PGPASSWORD="$PG_SUPER_PASSWORD" psql -h 127.0.0.1 -p 54450 -U postgres -d btl -Atc "$1"; }
wait_api() { for i in $(seq 40); do curl -fs -H 'Host: riksora.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8010/api/v1/auth/providers >/dev/null 2>&1 && return 0; sleep 1; done; return 1; }
status() {
  say "flag in app.env : $(flag_on && echo ON || echo off)   | running process: $(runtime_on && echo V2 || echo V1)"
  say "api memory      : $(systemctl --user show riksora-api -p MemoryCurrent -p MemoryPeak --value | tr '\n' ' ') (limit 8 GiB)"
  say "database size   : $(q "select pg_size_pretty(pg_database_size('btl'))")   checkpoints: $(q 'select count(*) from btl.tick_checkpoints')   sessions: $(q 'select count(*) from btl.tick_sessions')"
  say "job states      : $(q "select coalesce(string_agg(state||'='||n, ' '),'none') from (select state,count(*) n from btl.research_jobs group by 1) s")"
  F=$(journalctl --user -u riksora-api --since '-30 min' --no-pager 2>/dev/null | grep -c research_job_failed || true)
  R=$(journalctl --user -u riksora-api --since '-30 min' --no-pager 2>/dev/null | grep -c 'REFUSED_RECOVERY_LIMIT\|REFUSED_STATE_VERSION\|workerDeadline' || true)
  say "last 30 min     : research_job_failed=$F  recovery/state/deadline refusals=$R"
}
check() {
  local bad=0; gate() { if [ "$2" = ok ]; then say "PASS  $1"; else say "FAIL  $1 ($3)"; bad=1; fi; }
  systemctl --user is-active --quiet riksora-api && gate "api active" ok || gate "api active" no "service down"
  systemctl --user is-active --quiet riksora-pg && gate "database active" ok || gate "database active" no "service down"
  FREE=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9); [ "$FREE" -ge 30 ] && gate "disk free ${FREE} GB >= 30" ok || gate "disk free" no "${FREE} GB"
  MEM=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); [ "$MEM" -ge 2 ] && gate "MemAvailable ${MEM} GiB >= 2" ok || gate "memory" no "${MEM} GiB"
  SW=$(awk '/SwapTotal/{print $2}' /proc/meminfo); [ "$SW" -eq 0 ] && gate "no swap" ok || gate "no swap" no "swap present"
  BUSY=$(q "select count(*) from btl.research_jobs where state in ('QUEUED','RUNNING')"); [ "$BUSY" = "0" ] && gate "queue idle" ok || gate "queue idle" no "$BUSY job(s) in flight"
  NEW=$(find "$HOME/backups" -name 'prod-btl-*.dump' -mmin -60 2>/dev/null | head -1); [ -n "$NEW" ] && gate "verified backup younger than 60 min" ok || gate "fresh backup" no "run: backup_accounts.sh backup && drill"
  [ "$(q "select count(*) from btl.research_jobs where state in ('FAILED','RECONCILE_REQUIRED','EXPIRED')")" = "0" ] && gate "no failed job rows" ok || say "WARN  failed job rows exist (read status)"
  return $bad
}
smoke() { "$PY" "$HERE/v2_smoke.py" --expect "$1" | "$PY" -c "import json,sys; d=json.loads(sys.stdin.read()); print('smoke', 'PASS' if d['ok'] else 'FAIL', d['checkpointFormat'] if 'checkpointFormat' in d else '', [s['step'] for s in d['steps'] if not s['ok']]); sys.exit(0 if d['ok'] else 1)"; }
rollback() {
  if dry; then say "[dry-run] would remove '$FLAG' from $ENVF, restart riksora-api, smoke --expect v1"; return 0; fi
  [ -f "$ENVF" ] && grep -vx "$FLAG" "$ENVF" > "$ENVF.tmp" && chmod 600 "$ENVF.tmp" && mv "$ENVF.tmp" "$ENVF"
  systemctl --user restart riksora-api; wait_api || { say "API did not come back"; return 1; }; smoke v1
}
apply() {
  [ "${RIKSORA_V2_APPROVED:-}" = "YES-$(date -u +%F)" ] || { say "REFUSED: no explicit owner approval for today. The owner must set RIKSORA_V2_APPROVED=YES-$(date -u +%F)"; return 2; }
  check || { say "REFUSED: deployment gates failed"; return 3; }
  flag_on && { say "already ON"; return 0; }
  if dry; then say "[dry-run] would back up $ENVF, append '$FLAG', restart riksora-api, smoke --expect v2, and roll back on failure"; return 0; fi
  cp -p "$ENVF" "$ENVF.pre-v2-$(date -u +%Y%m%dT%H%M%SZ)"
  printf '%s\n' "$FLAG" >> "$ENVF"
  systemctl --user restart riksora-api
  if wait_api && smoke v2; then say "V2 ACTIVE and smoke PASS. Watch: v2_promote.sh status (48 h)"; return 0; fi
  say "V2 smoke FAILED: rolling back"; rollback; return 1
}
case "${1:-}" in status) status;; check) check;; apply) apply;; rollback) rollback;; *) sed -n 2,11p "$0"; exit 1;; esac
