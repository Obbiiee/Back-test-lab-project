# Workflow

Preserve domain separation and never weaken tests for PASS. Prefer official Lightweight Charts APIs and appropriate mature open source before unnecessary custom code; never copy proprietary TradingView or FX Replay source. The permanent loop below owns execution and completion gates.

> Two AI agents must not independently modify the same master files at the same time.

Product owner → architect/coordinator → narrow tasks with non-overlapping ownership → primary AI on master and secondary AI on disposable bundle → reviewed patch → controlled integration into master → full regression → master commit → GitHub.

Regenerate bundle before a task and verify hashes before review/integration. Master is authoritative. AI_BUNDLE may be stale; its edits never automatically modify or merge into master. Secondary AI returns a reviewed diff using FILE_MANIFEST mappings, not a replacement application tree. There is no ai:apply. Verify original master hashes before reviewing each proposed patch; manually integrate only authorized changes, then run full regression. The bundle intentionally omits dependencies/data and is not runnable production code.

Cleanup requires reference/build/test/bundle/history evidence before deletion or moving. Classify uncertain files and keep them. Record decisions in the audit; historical reports describe checkpoints and never override current context. Store new disposable browser evidence in ignored artifacts directories; keep explicitly referenced durable fixtures/reports. Current drawing-focused bundle is not a generic whole-repository package: narrow future tasks may require a reviewed allowlist update, never blind overwrite.

## Permanent one-phase loop and Definition of Done

This file is the sole workflow/Definition-of-Done/Git-policy authority. Operational values belong to [04_CURRENT_PHASE](04_CURRENT_PHASE.md); completed facts to [03_PHASE_HISTORY](03_PHASE_HISTORY.md); plans to [ROADMAP](../docs/ROADMAP.md). Do not copy those changing values here.

Read context → verify human authorization against current-phase authority → implement one phase → run required tests → browser verify product changes (record a justified exemption for documentation-only work) → review diff → update affected AI_CONTEXT and operational status → commit → normal GitHub push → verify remote HEAD equals local HEAD and working tree clean → report → STOP.

Do not declare completion when validation or push fails. Report the blocker and stop; do not force push, bypass protection or broaden scope. Prepare the validated context/status update for the checkpoint; if the checkpoint fails, report that it is incomplete and correct local status before retrying. Git verification after push is the completion evidence; avoid self-referential commit hashes inside their own commit.

Machine-checkable mandatory gates (these define policy, not current status):

```json
{
  "AUTHORITY": "workflow",
  "REQUIRE_HUMAN_AUTHORIZATION": true,
  "ONE_PHASE_ONLY": true,
  "REQUIRE_TESTS": true,
  "BROWSER_POLICY": "PRODUCT_CHANGES_REQUIRED_DOCS_ONLY_EXEMPT_WITH_REASON",
  "REQUIRE_DIFF_REVIEW": true,
  "REQUIRE_CONTEXT_STATUS_UPDATE": true,
  "REQUIRE_GITHUB_COMMIT": true,
  "REQUIRE_GITHUB_PUSH": true,
  "REQUIRE_REMOTE_HEAD_VERIFICATION": true,
  "REQUIRE_CLEAN_WORKING_TREE": true,
  "REQUIRE_STOP": true,
  "REQUIRE_NEXT_PROMPT": true
}
```

## NEXT-PROMPT REQUIREMENT

Every phase's final report must include a ready-to-copy next prompt derived from the operational pointer and roadmap. It must request explicit human authorization, require reading existing owners, specify only the supplied next-phase scope, retain protected boundaries, require validation/context update/Git checkpoint/remote verification, and end with STOP. When scope is undefined, the prompt requests scope definition first and forbids implementation until supplied. Never invent requirements or treat generating/sending a prompt as authorization. Human submission authorizes only the explicit scoped work; read-only planning does not authorize product implementation. No automatic dispatch or next-phase start.

Before reporting success, verify the next prompt agrees with current-phase authority. This self-propagating loop continues only through separate human-authorized tasks; the final roadmap milestone does not authorize skipping phases.
