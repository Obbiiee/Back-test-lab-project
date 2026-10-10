# Backtest Lab — Document Map

> **Purpose:** Menentukan dokumen mana yang menjawab pertanyaan apa agar thesis, design, architecture dan roadmap tidak menjadi sumber kebenaran yang saling bersaing.

| Question | Primary document |
|---|---|
| Why does Backtest Lab exist? What is the scientific thesis? | `BACKTEST_LAB_RESEARCH_THESIS.md` |
| What should users see and how should the product feel/work? | `PRODUCT_DESIGN_BLUEPRINT.md` |
| How should the software/system be structured? | `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` |
| What is the planned backend contract and guarded integration path? | [Same system blueprint — Phase 19 planning handoff](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#38-phase-19--backend-architecture-planning-handoff) |
| What Application/API intake is implemented, and what remains deferred? | [Same system blueprint — intake evidence](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#389-applicationapi-intake--implementation-evidence) and [Phase 19 completion audit](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#3810-phase-19-completion-audit) |
| What durable database, identity and ownership adapters actually exist? | Same system blueprint: [persistence](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#391-implemented-persistence-and-acceptance-evidence), [identity](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#401-implemented-identity-and-validation), [ownership/final audit](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#411-implemented-ownership-and-final-journey-audit) |
| What Phase 23 data/source rights, proposed delivery scope and decisions need review? | [Same system blueprint — market-data preparation](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#42-phase-23--market-data-service-preparation-planning-only) |
| What canonical market-data/fidelity/quality/registry requirements apply? | [Existing Market Data Standard](MARKET_DATA_STANDARD.md) |
| What sources, licenses, prices, payment triggers and two-lane strategy were researched? | [Same system blueprint — Phase 23 research](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#425-phase-23-authorized-research--provider-comparison) |
| How do scaling, data portability, AI, billing/entitlement and provider boundaries work? | `SCALING_DATA_AI_DECISIONS.md` |
| What security boundaries and launch-security gates apply? | `SECURITY_ARCHITECTURE.md` |
| What engineering contract must AI-generated code obey? | `AI_ENGINEERING_GUARDRAILS.md` |
| What is the canonical Trading Method / Session product contract? | [Trading Method specification](TRADING_METHOD_SESSION_SPEC.md) |
| What frozen trading UX handoff, prototype evidence and integration gate apply? | [The same Method/Session specification — handoff v1](TRADING_METHOD_SESSION_SPEC.md#frozen-trading-ux-specification-v1) |
| What did the post-v1 actual architecture/reference audit find? | [Phase 18.5 audit](PHASE18_5_ARCHITECTURE_REFERENCE_AUDIT.md) |
| What visual tokens, UI inventory, chooser and terminal rules apply? | [Phase 18.6 UI/design specification](PHASE18_6_UI_UX_DESIGN_SYSTEM.md) |
| What capabilities are planned and in what phase? | `ROADMAP.md` |
| What is authorized to implement now? | `../AI_CONTEXT/04_CURRENT_PHASE.md` |
| What complete Alpha target was accepted after local V2.2? | [Existing Alpha scope amendment](V2_ALPHA_FROZEN_SPEC.md#0a-human-approved-alpha-product-closure-amendment-2026-10-10); screen acceptance in Product Design Blueprint, supplemental decisions in Decision Register, OSS intake in Engineering Master Plan and checkpoint mapping in the existing ledger |
| What has actually been completed? | `../AI_CONTEXT/03_PHASE_HISTORY.md` |
| What workflow / Definition of Done governs implementation? | `../AI_CONTEXT/06_WORKFLOW_RULES.md` |

## Continuity entry points — V2.1 / STITCH / V2.2

Use the **existing** [master roadmap](ROADMAP.md#stitch-continuity--existing-oss-adoption-program-not-a-new-phase-or-release) to understand how completed V21-0…V21-6, uncompleted STITCH work, and separately authorized V2.2 connect. This is one product journey, **not** three competing roadmaps or a claim that STITCH is complete.

| Question | Existing owner |
| --- | --- |
| Which OSS projects were researched and what can they replace? | [STITCH-0 OSS audit](STITCH_0_OSS_REPLACEMENT_AUDIT.md) (historical inventory, not final donor selection) |
| How are current BTL, OpenAlgo and OpenCharts compared fairly? | [Data/Ops/Release Contract](V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md) and [Decision Register](V2_ALPHA_DECISION_REGISTER.md) |
| What is the order of S-1…S-7 work and acceptance? | [Frozen Execution Ledger](V2_ALPHA_FROZEN_EXECUTION_LEDGER.md) and [Work Execution Plan](V2_ALPHA_WORK_EXECUTION_PLAN.md) |
| What are the full professional drawing and indicator targets? | [Drawing Engine Spec](DRAWING_ENGINE_SPEC.md) and [Indicator Engine Spec](INDICATOR_ENGINE_SPEC.md) |
| What was actually completed in V2.1 and what is currently authorized? | [Phase History](../AI_CONTEXT/03_PHASE_HISTORY.md) and [Current Phase](../AI_CONTEXT/04_CURRENT_PHASE.md) |
| What is the bounded V2.2 precision/data/reliability plan? | [Master Roadmap](ROADMAP.md#v22-bounded-verification-program-future-separately-authorized) |

**Do not** promote old STITCH-0 donor preferences to final selection, mark professional targets complete based on Alpha minima, re-run V21-6, silently activate the frozen Alpha journey, or create a second planning/status owner. Historical reports and small notes remain preserved; deletion requires reference, history, bundle and test evidence per [workflow rules](../AI_CONTEXT/06_WORKFLOW_RULES.md).

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
