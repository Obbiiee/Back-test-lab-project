# v2 Alpha Journey Authorization Contract

Status: planning schema. This file does not authorize the journey by itself.

The sole operational owner remains `AI_CONTEXT/04_CURRENT_PHASE.md`. If the human later authorizes the complete frozen journey, that file must record a machine-readable block equivalent to:

```json
{
  "AUTHORIZATION_MODE": "FROZEN_JOURNEY",
  "JOURNEY_ID": "V2_ALPHA_V1",
  "JOURNEY_PLAN_VERSION": 1,
  "START_CHECKPOINT": "PF-0",
  "END_CHECKPOINT": "L-8",
  "AUTO_ADVANCE_AFTER_PASS": true,
  "ALLOW_SCOPE_EXPANSION": false,
  "ALLOW_ARCHITECTURE_REDESIGN": false,
  "HARD_STOP_POLICY": "V2_ALPHA_DECISION_REGISTER",
  "REVOCABLE_BY_HUMAN": true
}
```

Rules:
1. Human authorization must be explicit; planning completion never self-authorizes.
2. After authorization, PASS of one frozen checkpoint authorizes moving to the next ledger checkpoint without a new routine human approval.
3. Conditional/N-A checkpoints follow their frozen decision rule.
4. Failed acceptance remains inside the same checkpoint for diagnosis/repair.
5. A defined hard invalidation, unsafe/destructive permission boundary, unavailable required credential/private artifact, legal/rights uncertainty that blocks the current mode, or inability to prove Git completion stops auto-advance.
6. STOP records exact checkpoint/evidence and waits for the minimum necessary human decision/input.
7. Human may revoke journey authorization at any time; no new checkpoint begins after revocation.
8. Work may not reinterpret this schema from this file; the live values in 04_CURRENT_PHASE are authoritative.

This resolves governance for “plan your trade, trade your plan” without creating a second operational status owner.

## Roadmap relationship

`V2_ALPHA_V1` is a bounded cross-cutting engineering journey to the closed v2 Alpha/Beta-readiness review defined by its Frozen Execution Ledger. It is **not** authorization for ROADMAP Phases 23–75 as a numbered sequence and does not mark those phases complete.

The ROADMAP explicitly permits an explicit bounded multi-phase human authorization to live in the sole current-phase pointer. If the human authorizes `V2_ALPHA_V1`, only capabilities/checkpoints enumerated in the frozen ledger auto-advance. Roadmap capabilities outside the Alpha ledger—including later subscription/billing, teams, social/collaboration, advanced research, AI research assistant, live broker/data, forward testing and algorithmic-trading readiness—remain separately planned/unimplemented.

At journey completion L-8, factual phase/history mapping must be reconciled from what was actually implemented; no roadmap phase number is inferred merely from reaching L-8.
