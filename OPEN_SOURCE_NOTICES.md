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
