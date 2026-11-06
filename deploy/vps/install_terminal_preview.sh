#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-}"
ARTIFACT="${2:-}"
BUILD_ID="${3:-}"
PREVIEW_ROOT=/srv/riksora/previews/terminal
CADDYFILE=/etc/caddy/Caddyfile
CREDENTIAL_FILE=/root/.riksora-preview-owner
MIN_FREE_BYTES=$((32 * 1024 * 1024 * 1024))

fail() { printf 'PREVIEW_INSTALL_REFUSED: %s\n' "$*" >&2; exit 1; }
free_bytes() { df -B1 --output=avail /srv/riksora | tail -1 | tr -d ' '; }

[[ "$MODE" == install ]] || fail 'usage: sudo install_terminal_preview.sh install ARTIFACT_DIR BUILD_ID'
[[ $EUID -eq 0 ]] || fail 'must run through sudo by VPS administrator'
[[ -d "$ARTIFACT" && -f "$ARTIFACT/index.html" ]] || fail 'compiled artifact index.html missing'
[[ "$BUILD_ID" =~ ^[0-9a-f]{12,40}$ ]] || fail 'BUILD_ID must be a commit SHA prefix'
[[ -f "$CADDYFILE" && -x /usr/bin/caddy ]] || fail 'Caddyfile or Caddy executable missing'
[[ "$(free_bytes)" -ge "$MIN_FREE_BYTES" ]] || fail 'free disk is below the 32 GiB deployment guard'
if grep -q '# BEGIN RIKSORA TERMINAL PREVIEW' "$CADDYFILE"; then fail 'preview route already exists'; fi
grep -q 'DESIGN PREVIEW.*SYNTHETIC DATA.*NO LIVE ORDERS' "$ARTIFACT"/assets/*.js || fail 'synthetic preview badge missing from compiled bundle'
if grep -R -E 'https?://(api\.gold-api\.com|[^/]*exness|[^/]*dukascopy)' "$ARTIFACT"; then
  fail 'compiled bundle contains a market-data origin that is not allowed in this preview'
fi

RELEASE="$PREVIEW_ROOT/$BUILD_ID"
[[ ! -e "$RELEASE" ]] || fail "release already exists: $RELEASE"
install -d -o root -g root -m 0755 "$RELEASE"
cp -a "$ARTIFACT"/. "$RELEASE"/
find "$RELEASE" -type d -exec chmod 0755 {} +
find "$RELEASE" -type f -exec chmod 0644 {} +

if [[ ! -f "$CREDENTIAL_FILE" ]]; then
  umask 077
  password="$(openssl rand -hex 24)"
  printf 'username=owner\npassword=%s\n' "$password" > "$CREDENTIAL_FILE"
fi
chmod 0600 "$CREDENTIAL_FILE"
password="$(sed -n 's/^password=//p' "$CREDENTIAL_FILE")"
[[ ${#password} -ge 32 ]] || fail 'owner preview credential is malformed'
password_hash="$(/usr/bin/caddy hash-password --plaintext "$password")"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$CADDYFILE.before-terminal-preview-$stamp"
candidate="/etc/caddy/.Caddyfile.terminal-preview-$BUILD_ID"
cp -a "$CADDYFILE" "$backup"
python3 - "$CADDYFILE" "$candidate" "$RELEASE" "$password_hash" <<'PY'
import pathlib, sys

source, destination, release, password_hash = sys.argv[1:]
text = pathlib.Path(source).read_text()
if "# BEGIN RIKSORA TERMINAL PREVIEW" in text:
    raise SystemExit("PREVIEW_INSTALL_REFUSED: preview route already exists")
needle = "\t\t@private path /api /api/* /market /market/* /backend /backend/* /.git /.git/* /.env /.env* /src/* /node_modules/*"
if text.count(needle) != 1:
    raise SystemExit("PREVIEW_INSTALL_REFUSED: expected unique private route anchor not found")
route = f'''\t\t# BEGIN RIKSORA TERMINAL PREVIEW
\t\t@terminal_preview_root path /preview/terminal
\t\thandle @terminal_preview_root {{
\t\t\tredir /preview/terminal/ permanent
\t\t}}
\t\thandle_path /preview/terminal/* {{
\t\t\troot * {release}
\t\t\tbasic_auth {{
\t\t\t\towner {password_hash}
\t\t\t}}
\t\t\theader Cache-Control no-store
\t\t\theader X-Robots-Tag "noindex, nofollow"
\t\t\ttry_files {{path}} /index.html
\t\t\tfile_server
\t\t}}
\t\t# END RIKSORA TERMINAL PREVIEW
'''
pathlib.Path(destination).write_text(text.replace(needle, route + needle, 1))
PY
/usr/bin/caddy validate --config "$candidate" --adapter caddyfile || fail 'candidate Caddy configuration did not validate; live config unchanged'

homepage_before="$(curl -fsS https://riksora.com/ | sha256sum | cut -d' ' -f1)"
install -o root -g root -m 0644 "$candidate" "$CADDYFILE.next"
mv -f "$CADDYFILE.next" "$CADDYFILE"
if ! systemctl reload caddy || ! systemctl is-active --quiet caddy; then
  install -o root -g root -m 0644 "$backup" "$CADDYFILE.rollback"
  mv -f "$CADDYFILE.rollback" "$CADDYFILE"
  systemctl reload caddy || true
  fail "Caddy reload failed; original config restored from $backup"
fi

homepage_after="$(curl -fsS https://riksora.com/ | sha256sum | cut -d' ' -f1)"
anon_status="$(curl -sS -o /dev/null -w '%{http_code}' https://riksora.com/preview/terminal/)"
auth_body="$(mktemp)"
auth_status="$(curl --config <(printf 'user = "owner:%s"\n' "$password") -sS -o "$auth_body" -w '%{http_code}' https://riksora.com/preview/terminal/)"
auth_has_preview=no
grep -q 'Terminal Design Preview' "$auth_body" && auth_has_preview=yes
rm -f "$auth_body"
unset password
if [[ "$homepage_before" != "$homepage_after" || "$anon_status" != 401 || "$auth_status" != 200 || "$auth_has_preview" != yes ]]; then
  install -o root -g root -m 0644 "$backup" "$CADDYFILE.rollback"
  mv -f "$CADDYFILE.rollback" "$CADDYFILE"
  systemctl reload caddy || true
  fail "post-deploy guard failed; original config restored from $backup (homepage hashes equal=$([[ "$homepage_before" == "$homepage_after" ]] && echo yes || echo no), anonymous HTTP=$anon_status, owner HTTP=$auth_status, preview body=$auth_has_preview)"
fi
if [[ "$(free_bytes)" -lt "$MIN_FREE_BYTES" ]]; then
  install -o root -g root -m 0644 "$backup" "$CADDYFILE.rollback"
  mv -f "$CADDYFILE.rollback" "$CADDYFILE"
  systemctl reload caddy || true
  fail "disk reserve fell below 32 GiB; original config restored from $backup"
fi

printf 'PREVIEW_INSTALLED=%s\n' "$RELEASE"
printf 'PREVIEW_URL=https://riksora.com/preview/terminal/\n'
printf 'ANONYMOUS_HTTP=%s (expected 401)\n' "$anon_status"
printf 'OWNER_CREDENTIAL_FILE=%s (root-only; read on VPS to sign in)\n' "$CREDENTIAL_FILE"
printf 'BACKUP=%s\nROLLBACK: install -o root -g root -m 0644 %q %q && systemctl reload caddy\n' "$backup" "$backup" "$CADDYFILE"
printf 'HOMEPAGE_SHA256=%s\n' "$homepage_after"
