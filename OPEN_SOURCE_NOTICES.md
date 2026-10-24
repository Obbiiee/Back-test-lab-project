# Open-source chart components

Audit date: 2026-10-02. This inventory is not a substitute for upstream license files.

| Package | Source | License | Purpose / status |
| --- | --- | --- | --- |
| lightweight-charts 5.2.1 | https://github.com/tradingview/lightweight-charts | Apache-2.0 | Active chart engine: candles, native series, scales, crosshair, markers, price lines. |
| lightweight-charts-drawing 0.2.5 | https://github.com/deepentropy/lightweight-charts-drawing | MIT | Uninstalled in Phase 4. Unused adapters retained as non-executable `.reference.txt` files in `frontend/legacy/phase3`; not an official TradingView package. |

Lightweight Charts copyright: TradingView, Inc. Retain the package LICENSE and required attribution. The current chart displays its TradingView attribution link; do not remove it during migration. See the installed package README for attribution requirements.

Official toolkit/plugin candidates listed in docs/OFFICIAL_LIGHTWEIGHT_CHARTS_AUDIT.md are not installed by this audit. Add exact source revision, LICENSE and any NOTICE for each adopted component before distribution. Preserve upstream copyright headers and mark adapted source files as modified. The root upstream NOTICE path and a NOTICE in the currently installed chart package were not found during this audit; recheck the specific upstream distribution when copying examples.

No proprietary TradingView Advanced Charts / Charting Library code is included by this audit.

S-5 (2026-10-10): `frontend/src/tickAlpha/AlphaOrderPresentation.jsx` adapts only the Buy/Sell quote-button and reviewed-row presentation of OpenCharts `src/pages/trading/OrderPanel.tsx` and `src/components/trading-dialogs/OrderConfirmDialog.tsx`, exact revision `785d1f18cc1ca67b0246031b2b9a08cb5cb60264` (MIT, Copyright (c) 2024 OpenCharts Contributors). Changes are marked in the file. Exact upstream license is preserved in `frontend/public/licenses/opencharts-LICENSE.txt` and shipped with the build. No upstream API/store, broker order engine, one-click execution, margin/PnL arithmetic, data feed or auth is adopted. Exact source: https://github.com/dylanpersonguy/OpenCharts/tree/785d1f18cc1ca67b0246031b2b9a08cb5cb60264 . Existing STITCH audit owns adaptation evidence; this notice grants no market-data rights.

Phase 5 uses the installed Lightweight Charts 5.2.1 official Series Primitive and canvas APIs for an original application Trend Line primitive. Official documentation and the v5.2.1 trend-line example informed API usage; no upstream example source or community drawing engine was copied or added. TradingView attribution remains visible. See `docs/PHASE5_DRAWING_FOUNDATION.md` for API references and the boundary between chart infrastructure and application glue.

Release-candidate audit (2026-10-04): installed Lightweight Charts remains 5.2.1. Its [tagged upstream NOTICE](https://raw.githubusercontent.com/tradingview/lightweight-charts/v5.2.1/NOTICE) was verified and preserved in frontend/public/licenses/NOTICE.txt. Installed chart/React/React DOM/Scheduler LICENSE bytes are copied into public/licenses and carried into dist. Existing chart attribution remains visible. This inventory is not a legal certification or a market-data redistribution license; historical provider limits remain in docs/HISTORICAL_XAU.md.

Transitive chart notices: fancy-canvas 2.1.0 declares MIT in installed package metadata; its distribution omits LICENSE, so public/licenses/fancy-canvas-LICENSE.txt preserves the inspected upstream https://raw.githubusercontent.com/tradingview/fancy-canvas/master/LICENSE. The chart README identifies incorporated tslib helpers (Microsoft, BSD Zero Clause); public/licenses/tslib-LICENSE.txt preserves https://raw.githubusercontent.com/microsoft/tslib/main/LICENSE.txt. These two source URLs are unversioned upstream references, not a claim of matching tagged source revision.

Alpha supplemental S-2 (2026-10-11): `frontend/src/drawings/rayGeometry.js` adapts only endpoint normalization from `deepentropy/lightweight-charts-drawing`, `src/core/scene/lines.ts:sceneExtendedSegment`, exact revision `72290d3165682ec7bd28f96af7f9354184982dda` (package0.5.1, MIT Copyright (c)2026deepentropy). Modified for offscreen anchors. Exact upstream license is preserved at `frontend/public/licenses/lightweight-charts-drawing-ray-LICENSE.txt` and shipped by Vite; NOTICE records the pin. No upstream full runtime, parser, unrelated tools, host application or market data is adopted. Existing manager/history/strict JSON/coordinate bridge remain authoritative. The earlier0.2.5 removal record above remains historical evidence.


Google adapter (2026-10-17): backend HTTPX OAuth0.17.0, MIT, exact PyPI distribution https://pypi.org/project/httpx-oauth/0.17.0/ and upstream https://github.com/frankie567/httpx-oauth . Installed distribution LICENSE bytes retained in docs/licenses/httpx-oauth-0.17.0-LICENSE.txt. SDK handles authorization-code/PKCE/token HTTP exchange; existing PyJWT2.15.1/cryptography performs Google signature/claims verification. No SDK example source or Google artwork copied. No actual Google credential or acceptance implied.

Brand fonts (2026-10-17): `frontend/src/assets/fonts/` ships unmodified latin-subset woff2 files from Fontsource 5.3.0 npm packages: `@fontsource-variable/inter` (Inter, Copyright 2016 The Inter Project Authors) and `@fontsource/ibm-plex-mono` (IBM Plex Mono 400/500, Copyright 2017 IBM Corp.), both SIL Open Font License 1.1. Exact license texts are preserved in `frontend/public/licenses/inter-OFL.txt` and `ibm-plex-mono-OFL.txt` and shipped with the build. Files are bundled by Vite; no runtime package dependency or remote font request is added.


## Optional Odoo Community business runtime

Odoo19 Community source: https://github.com/odoo/odoo/tree/dbec872e39b030828e7cd22aae1d39d2da87c29e (LGPL-3). It runs separately; upstream source/dependencies/QA credentials are not committed or included in the Backtest source archive. The authored btl_business addon declares LGPL-3; license text is retained at integrations/odoo/LICENSE. Native CRM/Invoicing are upstream Community modules; no Enterprise source is copied. No tax/statutory accounting certification is implied.

Optional browser QA (2026-10-24): Microsoft Playwright / @playwright/test1.64.1, Apache-2.0, https://github.com/microsoft/playwright . Exact optional graph/integrities are retained in frontend/tests/browser-tools/package-lock.json. Installed npm distributions retain their own LICENSE/NOTICE. No upstream source was copied into the application; browsers and tooling are installed separately, excluded from the source release archive, and never loaded by product runtime. Software licensing does not license historical market data.
