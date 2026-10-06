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
