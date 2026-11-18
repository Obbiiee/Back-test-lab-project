# Git audit before any push (2026-11-18)

Scope: the 124 local commits on `claude/dual-engine-v1-20261114` that are not on GitHub (`origin/claude/dual-engine-v1-20261114`). Nothing was pushed, rewritten, reset or deleted. All checks were read-only except the creation of a backup bundle and a dry-run clone under `~/backups` (outside the repository, mode 0700).

## 1. Findings
| Check | Result |
|---|---|
| Commits ahead of the remote | 124 (123 at the previous report plus the latest local commit); 122 authored `obi`, 2 `Claude` |
| Secrets, exact-value search | **None.** The Google client id/secret/redirect URI, the three PostgreSQL passwords and the auth secret from `~/.config` do not occur in any commit patch |
| Secrets, patterns | **None**: private-key blocks, AWS key ids, Google API keys, GitHub/Slack tokens, Midtrans keys, `GOCSPX-` secrets, JWT-shaped tokens: 0 matches. Assignment-like `password/secret/token = "…"` with a real-looking value: 0 after removing obvious test placeholders |
| Market data / large binaries in the diff | none found by this audit's patterns (the publish script and `.gitignore` already exclude them); a separate size review was not part of this audit |
| Owner's personal name | In **three** historical commits, in two files only: `5137d46` (adds the full legal name to `frontend/src/site/siteConfig.js`, plus the city-level address and the refund text), `880995d` (removes it from the config; adds a guard test that still contained a name part) and `4b2f2ad` (removes that part from the test). **Not present in any file at HEAD**, not in any commit message |
| Personal network address | `docs/DUAL_ENGINE_FINAL_DECISION_20261114.md` (HEAD, one line) records the client IP of another login session on the VPS (very likely the owner's own connection). Introduced in `f96a4e2` |
| Server address | `deploy/site/README.md` (HEAD) names the VPS IP. The same address is public through the `riksora.com` A record, so this is informational, not a leak |
| Contact email | `risoralabs@gmail.com` is the intended public support address (site config and docs). The commit author email is the one already used on the remote's earlier commits |
| Work lost? | No. Working tree clean at `bb07aeb` before this audit; backup bundle verified |

Note on the earlier private-term list: it held only one part of the name; the other parts were read from `5137d46` itself. The sanitization below covers all three parts.

## 2. Backup (done)
`~/backups/riksora-pre-sanitize-bb07aeb.bundle` (`git bundle --all`, "records a complete history", 84 refs) with its `.sha256`. Restore: `git clone riksora-pre-sanitize-bb07aeb.bundle restored`.

## 3. Sanitization options (none applied)
**Important fact:** the 124 commits were never pushed. Rewriting them does not rewrite any published history, so after sanitization the push is an ordinary fast-forward on top of the current remote head, **no force-push needed**.

| Option | Effect | Cost / risk |
|---|---|---|
| **A. Sanitize, then push (recommended)** | `git filter-branch --tree-filter` limited to `<remote-base>..HEAD` replaces the three name parts in the two files and the client IP in the one doc line | All 124 commit hashes after the first changed commit change; commit count, subjects, authors, dates and bodies stay identical |
| B. Push as is | Publishes the full name in `5137d46`, `880995d`, `4b2f2ad` and the client IP | Irreversible once public (clones/caches) even if later deleted |
| C. Squash the range into a few commits | Smallest history, removes the name from history as a side effect | Loses the per-step history that the audit documents rely on |
| D. Do not push | Keep local, rely on the bundle backup | CI cannot run; no off-machine copy except the bundle |

**Dry-run of option A (done, in `~/backups/sanitize-dryrun`, a clone; the original repository is untouched, HEAD still `bb07aeb`):**
* 124 of 124 commits rewritten; subject, author, date and body identical for every commit: **true**.
* Name parts left in the sanitized patch text: **0**. Client IP left: **0**.
* Tree difference between the original HEAD and the sanitized HEAD: **one line** in `docs/DUAL_ENGINE_FINAL_DECISION_20261114.md` (the IP). Nothing else differs, so no content is lost.
* The filter script (`~/backups/sanitize-tree.sh`) contains the name parts, so it lives outside the repository (mode 0700) and must not be committed.

Procedure the owner can authorize (do not run without that authorization):
1. `git bundle create` again if new commits were added (the current bundle covers `bb07aeb`; later commits are not in it).
2. In the real repository: `FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --tree-filter 'sh ~/backups/sanitize-tree.sh' -- <remote-base>..HEAD` (`<remote-base>` = `git rev-parse origin/claude/dual-engine-v1-20261114`).
3. Re-run the scan (exact secrets and name parts) on the rewritten range; compare the tree with the pre-rewrite HEAD (expect only the IP line); run the local test list; then `git push origin claude/dual-engine-v1-20261114` (no `--force`).
4. Keep the bundle for 30 days, then delete.

## 3b. The commit author email
Every commit carries the author's own email. It already appears on the remote's earlier commits, so pushing adds nothing new; changing it would be a separate rewrite and was not requested.

## 4. Local test list (CI substitute)
GitHub Actions (`product-v1-backend`, `product-v1-browser`, `exness-monthly-parquet`) needs a push. The same commands were run locally on PostgreSQL 17 (CI uses 16); see the final report for the results. They do not replace a CI run on PostgreSQL 16.
