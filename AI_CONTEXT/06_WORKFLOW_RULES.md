# Workflow

1. One narrow authorized phase at a time; inspect before modifying.
2. Prefer official Lightweight Charts APIs and appropriate mature open source before unnecessary custom code. Never copy proprietary TradingView or FX Replay source.
3. Preserve domain separation; never weaken tests for PASS.
4. Run required regression, browser-verify interaction changes, produce report.
5. Commit completed work, normal push to configured GitHub branch, verify success, STOP. No force push or unrequested next phase.

> Two AI agents must not independently modify the same master files at the same time.

Product owner → architect/coordinator → narrow tasks with non-overlapping ownership → primary AI on master and secondary AI on disposable bundle → reviewed patch → controlled integration into master → full regression → master commit → GitHub.

Regenerate bundle before a task and verify hashes before review/integration. Master is authoritative. AI_BUNDLE may be stale; its edits never automatically modify or merge into master. Secondary AI returns a reviewed diff using FILE_MANIFEST mappings, not a replacement application tree. There is no ai:apply. Verify original master hashes before reviewing each proposed patch; manually integrate only authorized changes, then run full regression. The bundle intentionally omits dependencies/data and is not runnable production code.

Cleanup requires reference/build/test/bundle/history evidence before deletion or moving. Classify uncertain files and keep them. Record decisions in the audit; historical reports describe checkpoints and never override current context. Store new disposable browser evidence in ignored artifacts directories; keep explicitly referenced durable fixtures/reports. Current drawing-focused bundle is not a generic whole-repository package: narrow future tasks may require a reviewed allowlist update, never blind overwrite.
