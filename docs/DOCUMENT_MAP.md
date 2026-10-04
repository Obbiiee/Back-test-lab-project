# Backtest Lab — Document Map

> **Purpose:** Menentukan dokumen mana yang menjawab pertanyaan apa agar thesis, design, architecture dan roadmap tidak menjadi sumber kebenaran yang saling bersaing.

| Question | Primary document |
|---|---|
| Why does Backtest Lab exist? What is the scientific thesis? | `BACKTEST_LAB_RESEARCH_THESIS.md` |
| What should users see and how should the product feel/work? | `PRODUCT_DESIGN_BLUEPRINT.md` |
| How should the software/system be structured? | `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` |
| What is the planned backend contract and guarded integration path? | [Same system blueprint — Phase 19 planning handoff](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#38-phase-19--backend-architecture-planning-handoff) |
| How do scaling, data portability, AI, billing/entitlement and provider boundaries work? | `SCALING_DATA_AI_DECISIONS.md` |
| What security boundaries and launch-security gates apply? | `SECURITY_ARCHITECTURE.md` |
| What engineering contract must AI-generated code obey? | `AI_ENGINEERING_GUARDRAILS.md` |
| What is the canonical Trading Method / Session product contract? | [Trading Method specification](TRADING_METHOD_SESSION_SPEC.md) |
| What frozen trading UX handoff, prototype evidence and integration gate apply? | [The same Method/Session specification — handoff v1](TRADING_METHOD_SESSION_SPEC.md#frozen-trading-ux-specification-v1) |
| What did the post-v1 actual architecture/reference audit find? | [Phase 18.5 audit](PHASE18_5_ARCHITECTURE_REFERENCE_AUDIT.md) |
| What visual tokens, UI inventory, chooser and terminal rules apply? | [Phase 18.6 UI/design specification](PHASE18_6_UI_UX_DESIGN_SYSTEM.md) |
| What capabilities are planned and in what phase? | `ROADMAP.md` |
| What is authorized to implement now? | `../AI_CONTEXT/04_CURRENT_PHASE.md` |
| What has actually been completed? | `../AI_CONTEXT/03_PHASE_HISTORY.md` |
| What workflow / Definition of Done governs implementation? | `../AI_CONTEXT/06_WORKFLOW_RULES.md` |

## Mental Model

    RESEARCH THESIS
    WHY / scientific foundation
            ↓
    PRODUCT DESIGN BLUEPRINT
    WHAT THE USER EXPERIENCES
            ↓
    SYSTEM ARCHITECTURE BLUEPRINT
    HOW THE SYSTEM IS STRUCTURED
            ↓
    SCALING / DATA / AI DECISIONS
    HOW IT GROWS WITHOUT LOSING DATA OR BOUNDARIES
            ↓
    SECURITY ARCHITECTURE
    WHAT MUST REMAIN PROTECTED
            ↓
    AI ENGINEERING GUARDRAILS
    HOW AI-ASSISTED CODE MUST BE BUILT & VALIDATED
            ↓
    ROADMAP
    WHEN CAPABILITIES ARE PLANNED
            ↓
    CURRENT PHASE
    WHAT IS AUTHORIZED NOW
            ↓
    CODE + TESTS + COMPLETED HISTORY
    WHAT ACTUALLY EXISTS

## Governance

Planning documents may evolve as evidence and product decisions improve.

However:
- a blueprint does not authorize implementation;
- security and AI-engineering contracts apply cross-cutting whenever relevant, but do not authorize a phase;
- a thesis does not change current phase;
- roadmap planning does not prove a feature exists;
- completed history records facts;
- current-phase authority controls implementation authorization.

When documents conflict, resolve the conflict explicitly rather than silently allowing multiple truths.
