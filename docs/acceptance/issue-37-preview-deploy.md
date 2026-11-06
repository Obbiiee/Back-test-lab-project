# Issue #37 — isolated terminal preview deployment

The preview build is an independent static entry built from the Claude PR #36 frontend. It uses a deterministic 360-candle synthetic fixture, the shared PR #36 chart/drawing/indicator components, browser-local storage under `riksora-design-preview:claude-pr36:v1`, and no market or financial API calls. Its deployment path is separate from `/`, `/login/`, and the current release symlink.

## Build and checks

From the repository root:

```sh
cd frontend
npm ci
npm run build:terminal-preview
```

This writes `frontend/dist-terminal-preview/`, with assets rooted at `/preview/terminal/`. The installer rejects a build without the persistent synthetic/no-orders badge, rejects known external/paid market-feed origins, and checks that the host keeps at least 32 GiB free.

## Administrator install

The installer modifies only `/etc/caddy/Caddyfile` by inserting the dedicated route before the existing private-path guard, adds a versioned static directory under `/srv/riksora/previews/terminal/`, validates the candidate Caddyfile, then reloads Caddy. It does not restart the backend or alter the homepage release symlink. The installer generates a random owner password, stores it in `/root/.riksora-preview-owner` with mode 0600, and stores only its Caddy bcrypt hash in the Caddyfile.

Run from the VPS checkout after the build:

```sh
sudo bash deploy/vps/install_terminal_preview.sh install \
  "$PWD/frontend/dist-terminal-preview" \
  "$(git rev-parse --short=40 HEAD)"
```

Read the generated owner login on the VPS with `sudo cat /root/.riksora-preview-owner`. Do not copy it into GitHub, shell history, or a public channel. Caddy returns HTTP 401 to anonymous requests and serves the preview only after Basic Auth. HTTPS is already terminated by the existing site server.

## Rollback

The installer records the exact old Caddyfile path and prints a rollback command. Restore that backup and reload only Caddy:

```sh
sudo install -o root -g root -m 0644 /etc/caddy/Caddyfile.before-terminal-preview-<UTC_TIMESTAMP> /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

The versioned static preview directory and evidence are retained; rollback does not delete files. A redeploy uses a new build SHA and must not overwrite an existing release.

## Post-install acceptance

Confirm `/preview/terminal/` is 401 without credentials, 200 with the generated owner credentials, and visibly shows the preview badge. Confirm the returned HTML differs from `/`, while homepage SHA-256 remains unchanged. Test the actual desktop and mobile flows before treating this as `VISUAL_PREVIEW_LIVE`; build success alone is not deployment acceptance.
