#!/bin/bash
# Build the public site and publish it to ~/site/dist (served by Caddy). Refuses to publish market data or an incomplete configuration.
# Usage: deploy/site/publish.sh            (release build: needs `npm run verify:site` to pass)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PATH="$HOME/tools/node/bin:$PATH"
cd "$ROOT/frontend"
npm run test:site && npm run test:account-plan
npm run lint
npm run build:release                       # runs the release gate first (business facts + legal approvals)
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
rsync -a --delete --exclude 'market/' --exclude 'sample_*.csv' --exclude '*.map' dist/ "$STAGE/"
# safety: market data must never be published (data rights are UNKNOWN), nor any file containing a private term
if [ -e "$STAGE/market" ] || ls "$STAGE"/sample_*.csv >/dev/null 2>&1; then echo "REFUSED: market data in the publish set"; exit 1; fi
PRIVATE="$HOME/.config/riksora-private-terms.txt"          # one term per line, OUTSIDE the repository (e.g. the owner's personal name); never published
if [ -s "$PRIVATE" ] && grep -rIqiF -f "$PRIVATE" "$STAGE"; then echo "REFUSED: a private term was found in the publish set"; exit 1; fi
mkdir -p "$HOME/site"
[ -d "$HOME/site/dist" ] && rm -rf "$HOME/site/dist.prev" && mv "$HOME/site/dist" "$HOME/site/dist.prev"      # one-step rollback
rsync -a "$STAGE/" "$HOME/site/dist/"
echo "published $(find "$HOME/site/dist" -type f | wc -l) files to ~/site/dist (previous version kept in ~/site/dist.prev)"
