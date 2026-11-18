#!/usr/bin/env bash
# Disposable loopback HTTPS, synthetic identity fixture and user-space PostgreSQL.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
qa_dir=$(mktemp -d /tmp/riksora-mi-browser.XXXXXX)
qa_bin=${BTL_PG_BIN:-"$HOME/tools/pg17/bin"}
qa_python=${BTL_QA_PYTHON:-"$HOME/tools/venv313/bin/python"}
qa_node=${BTL_QA_NODE:-"$HOME/tools/node/bin/node"}
qa_pid=
cleanup() {
  if [ -n "$qa_pid" ]; then kill "$qa_pid" 2>/dev/null || true; wait "$qa_pid" || true; fi
  "$qa_bin/pg_ctl" -D "$qa_dir/data" -m fast -w stop >/dev/null 2>&1 || true
  rm -f -- "$qa_dir/browser.json" "$qa_dir/tls.key"
}
trap cleanup EXIT
printf 'MI browser evidence directory: %s\n' "$qa_dir"
"$qa_bin/initdb" -D "$qa_dir/data" --auth-local=trust --auth-host=reject --no-instructions >/dev/null
"$qa_bin/pg_ctl" -D "$qa_dir/data" -l "$qa_dir/postgres.log" -o "-c listen_addresses='' -k $qa_dir -p 55437" -w start >/dev/null
openssl req -x509 -newkey rsa:2048 -keyout "$qa_dir/tls.key" -out "$qa_dir/tls.crt" -days 1 -subj /CN=localhost -nodes >/dev/null 2>&1
export BTL_TEST_DATABASE_URL="host=$qa_dir port=55437 dbname=postgres"
cd "$repo/backend"
"$qa_python" -m tests.mi_browser_server "$qa_dir" >"$qa_dir/api.log" 2>&1 &
qa_pid=$!
cd "$repo"
for i in $(seq 1 60); do
  if test -s "$qa_dir/browser.json"; then break; fi
  if ! kill -0 "$qa_pid" 2>/dev/null; then tail -25 "$qa_dir/api.log"; exit 1; fi
  sleep 0.3
done
test -s "$qa_dir/browser.json"
export MI_BROWSER_QA="$qa_dir"
export MI_CHROMIUM=${MI_CHROMIUM:-"$repo/frontend/tests/browser-tools/browsers/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell"}
timeout 115 "$qa_node" frontend/tests/qa/mi-local-e2e.mjs | tee "$qa_dir/browser-results.jsonl"
"$qa_bin/psql" -X -h "$qa_dir" -p 55437 -d postgres -At <<'SQL' | tee "$qa_dir/worker-smoke.json"
WITH samples AS (
  SELECT convert_from(worker_metrics,'UTF8')::jsonb AS metrics
  FROM btl.research_jobs
  WHERE operation='replay' AND state='SUCCEEDED' AND worker_metrics IS NOT NULL
)
SELECT json_build_object(
  'completedJobs', count(*),
  'reportedCpuSeconds', round(sum((metrics->>'cpuNs')::numeric) / 1e9, 6),
  'reportedPeakRssMiB', round(max((metrics->>'processPeakRssBytes')::numeric) / 1048576, 2)
) FROM samples;
SQL
