# Open-source chart components

Audit date: 2026-10-02. This inventory is not a substitute for upstream license files.

| Package | Source | License | Purpose / status |
| --- | --- | --- | --- |
| lightweight-charts 5.2.1 | https://github.com/tradingview/lightweight-charts | Apache-2.0 | Active chart engine: candles, native series, scales, crosshair, markers, price lines. |
| lightweight-charts-drawing 0.2.5 | https://github.com/deepentropy/lightweight-charts-drawing | MIT | Uninstalled in Phase 4. Unused adapters retained as non-executable `.reference.txt` files in `frontend/legacy/phase3`; not an official TradingView package. |

Lightweight Charts copyright: TradingView, Inc. Retain the package LICENSE and required attribution. The current chart displays its TradingView attribution link; do not remove it during migration. See the installed package README for attribution requirements.

Official toolkit/plugin candidates listed in docs/OFFICIAL_LIGHTWEIGHT_CHARTS_AUDIT.md are not installed by this audit. Add exact source revision, LICENSE and any NOTICE for each adopted component before distribution. Preserve upstream copyright headers and mark adapted source files as modified. The root upstream NOTICE path and a NOTICE in the currently installed chart package were not found during this audit; recheck the specific upstream distribution when copying examples.

No proprietary TradingView Advanced Charts / Charting Library code is included by this audit.

Phase 5 uses the installed Lightweight Charts 5.2.1 official Series Primitive and canvas APIs for an original application Trend Line primitive. Official documentation and the v5.2.1 trend-line example informed API usage; no upstream example source or community drawing engine was copied or added. TradingView attribution remains visible. See `docs/PHASE5_DRAWING_FOUNDATION.md` for API references and the boundary between chart infrastructure and application glue.

Release-candidate audit (2026-10-04): installed Lightweight Charts remains 5.2.1. Its [tagged upstream NOTICE](https://raw.githubusercontent.com/tradingview/lightweight-charts/v5.2.1/NOTICE) was verified and preserved in frontend/public/licenses/NOTICE.txt. Installed chart/React/React DOM/Scheduler LICENSE bytes are copied into public/licenses and carried into dist. Existing chart attribution remains visible. This inventory is not a legal certification or a market-data redistribution license; historical provider limits remain in docs/HISTORICAL_XAU.md.

Transitive chart notices: fancy-canvas 2.1.0 declares MIT in installed package metadata; its distribution omits LICENSE, so public/licenses/fancy-canvas-LICENSE.txt preserves the inspected upstream https://raw.githubusercontent.com/tradingview/fancy-canvas/master/LICENSE. The chart README identifies incorporated tslib helpers (Microsoft, BSD Zero Clause); public/licenses/tslib-LICENSE.txt preserves https://raw.githubusercontent.com/microsoft/tslib/main/LICENSE.txt. These two source URLs are unversioned upstream references, not a claim of matching tagged source revision.
