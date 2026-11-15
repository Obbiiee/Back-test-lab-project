# RIKSORA — source protection and recovery (2026-11-15)

Status: operational note, not an architecture authority.

State when written: branch `claude/dual-engine-v1-20261114`, HEAD `37654a81c78b681f6af9093f923f98867586cc10`, tree `fa8f8af3a3b3b37dbd90fa1aaccc91f38e04f313`, working tree clean, 0 stashes, 61 commits ahead of `origin/claude/dual-engine-v1-20261114` (0 behind). Nothing was reset, rebased, force-pushed or discarded.

Artifacts (on the VPS, directory `~/backups`, listed with SHA-256 in `~/backups/SHA256SUMS.txt`):
| File | Content | SHA-256 |
|---|---|---|
| `riksora-bundles/riksora-dual-engine-FULL-37654a8.bundle` | complete history of the branch, self-contained (82 MB) | `8bbf01e631d8c8defed5d38eda48c18ff7f53ce85ea8dc6212fbe2cc4bf901ca` |
| `riksora-bundles/riksora-dual-engine-37654a8.bundle` | only the 61 local commits; needs `origin/claude/dual-engine-v1-20261114` at `685d6c5ea16c94e4ce57cce4cfcd142d083fbb64` | `39563516b56f6977c2d48840df890a01634848c70bb16699b57c2f461ca0fcce` |
| `evidence/riksora-evidence-2026-11-15-37654a8.tgz` | `docs/benchmarks` and `docs/acceptance` (reports, QA evidence, browser artifacts) | `fe978740646fec141810ef3bfb8d244e6d2943a9141776c10aa5919e17865d7b` |
Verification done: `git bundle verify` OK; a fresh `git clone` from the full bundle reproduces HEAD and the same tree hash and passes `git fsck`.

**This is NOT disaster recovery.** All copies are on the same VPS disk as the working tree. Until a copy exists off this machine, a disk or account loss loses the work. Raw market data is not in Git by rule; its originals are on the owner's laptop.

Copy off the VPS (owner, from the laptop; no secret is needed on the VPS):
`scp riksora_vps1:backups/riksora-bundles/riksora-dual-engine-FULL-37654a8.bundle .` then `sha256sum` against the value above.
Restore: `git clone riksora-dual-engine-FULL-37654a8.bundle riksora -b claude/dual-engine-v1-20261114`, then `git remote set-url origin https://github.com/Obbiiee/Back-test-lab-project.git`. Publish without force: `git push origin claude/dual-engine-v1-20261114` (the remote branch is an ancestor of the local one, so it is a fast-forward) using the owner's credential.
