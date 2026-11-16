# riksora.com static site: deployment runbook (2026-11-16)

Status: prepared, **not running**. DNS already points `riksora.com` and `www.riksora.com` to this VPS (A record 172.255.209.213; nameservers `ns1/ns2.domainesia.net`). Ports 80 and 443 do not answer yet, and the developer user cannot bind them without one root action.

## What is served
Only the static build of `frontend/` (`npm run build:release` output) from `~/site/dist`. The application API and the QA stack are not exposed (`/api/*` returns 404). The site is in **preview mode** (`SITE.launchState = 'preview'`): product, prices and policies are shown and sign-in is replaced by a beta-access notice.

## One-time root steps (owner)
1. Allow Caddy to bind 80 and 443 (narrow option, only that binary):
   `sudo setcap cap_net_bind_service=+ep /home/developer/tools/caddy/caddy`
   (Alternative for the whole machine: `echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/99-unprivileged-ports.conf && sudo sysctl --system`. It lets every user on the host bind ports from 80 up.)
2. Open inbound TCP 80 and 443: in the VPS provider's firewall/security-group panel, and in `ufw` only if it is active (`sudo ufw status`; `sudo ufw allow 80,443/tcp`). SSH rules stay untouched.
3. (Optional) put an email for certificate-expiry notices in `~/.config/riksora-site.env` as `ACME_EMAIL=...` and add `email {$ACME_EMAIL}` to the Caddyfile global block.

## Start (agent or owner, no root)
```
mkdir -p ~/.config/systemd/user ~/site
cp deploy/site/riksora-site.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now riksora-site
journalctl --user -u riksora-site -n 50 --no-pager
```
Caddy obtains the Let's Encrypt certificate automatically on the first request (needs ports 80/443 reachable from the internet).

## Verify (from any network)
`curl -sI https://riksora.com` returns 200 with `strict-transport-security`; `curl -sI http://riksora.com` redirects to https; `https://www.riksora.com` redirects to the apex.

## Update the site
Rebuild (`cd frontend && npm run build:release`), copy `frontend/dist/` to `~/site/dist/` (rsync), no restart needed. Keep the previous `dist` for rollback.

## Before pointing Midtrans at it
`npm run verify:site` must report "site configuration complete" (business facts, legal approvals, payment methods, tax note). Email: the MX record of `riksora.com` points to itself, so no mailbox exists on this domain; use an existing mailbox or configure mail first.
## Rollback
`systemctl --user stop riksora-site` takes the site offline; DNS can stay.
