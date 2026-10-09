# Backtest Lab

Aplikasi utama: React 19, Vite 8, TradingView Lightweight Charts 5.2.1.
Default v1: `frontend/index.html` → `frontend/src/main.jsx` → `FigmaWorkspace.jsx`; local tick alpha is an explicit opt-in route.
Source produksi tetap di `frontend/src/`; backend tidak diperlukan untuk workspace default v1.

Arsip XAUUSD sekitar sepuluh tahun: 3.486.461 candle M1, sebelas timeframe, dimuat bertahap dari `frontend/public/market/decade/`. Sumber/batas data: [HISTORICAL_XAU](docs/HISTORICAL_XAU.md).

Kemampuan dan batas produk aktual dimiliki oleh [status repository](AI_CONTEXT/01_PROJECT_STATE.md); laporan fase lama merekam checkpoint historis. [Panduan release lokal](docs/V1_RELEASE.md) menjelaskan cara menjalankan, penyimpanan dan bukti penerimaan.

## Menjalankan aplikasi

```text
cd frontend
npm ci
npm run dev
```

Buka alamat yang ditampilkan Vite. Harga live memerlukan internet; simulasi historis berjalan di browser.

## Struktur dan validasi

- `frontend/src/`: satu implementasi produksi.
- `frontend/tests/`: regresi dan fixture browser; [daftar command](AI_CONTEXT/07_TEST_COMMANDS.md).
- `frontend/scripts/`: download data dan generator AI bundle.
- `frontend/legacy/phase3/`, `legacy/`: arsip, bukan aplikasi aktif.
- `backend/`, `data/`: backend/domain dan sample terpisah; local tick alpha memakai layanan loopback + PostgreSQL, sementara default v1 tetap independen.
- `AI_CONTEXT/`: konteks aktual; [mulai di sini](AI_CONTEXT/00_START_HERE.md).
- `docs/`: laporan historis dan keputusan; [indeks](docs/README.md).
- `AI_BUNDLE/`, dependencies, build/cache: output lokal yang diabaikan Git.

[Audit repository](docs/PHASE7_5_REPOSITORY_AUDIT.md) menjelaskan bukti cleanup. Jangan membuat salinan source utama atau memakai arsip sebagai entrypoint.

## Secondary AI

Dari `frontend/`, jalankan `npm run ai:bundle` lalu `npm run ai:bundle:verify`.
Bundle kecil adalah referensi task spesifik, bukan aplikasi runnable. Claude mengembalikan patch untuk review; integrasi manual di master harus diikuti seluruh regresi. Tidak ada automatic apply atau API AI.

## Backend standalone (opsional)

```text
cd backend
python -m unittest discover -s tests -t . -v
```

API lama: buat virtual environment, install `requirements.txt`, lalu `uvicorn api.main:app --reload --port 8000`. Konsumen UI lamanya tersimpan di arsip Phase 3; menyalakan API tidak mengaktifkan UI tersebut pada workspace utama.

## Local tick Functional Alpha (V2.1)

Open `/?tick-alpha=local` on the configured loopback frontend (5173, or isolated QA 5196), with the separately configured local PostgreSQL and loopback service running. See [authoritative run/test commands](AI_CONTEXT/07_TEST_COMMANDS.md) and [existing Section 43 scope/evidence](docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md). Service startup does not migrate/reset a database; choose an accepted isolated target and apply the existing checksum migrations explicitly. Credentials stay in the local environment.

Create a Method, create/reopen its Session, use chart/drawings/indicators and tick replay, review/confirm an intent, then reveal ticks to observe its actual simulated lifecycle. Trading/Analysis read the same committed event chain; reload reopens the database Session. Drawing geometry persists separately per Session; indicator settings currently reset on reload. The default v1 route retains its historical candle-modelled workspace.

This alpha uses authored synthetic XAUUSD/USD Bid/Ask evidence and exact simulated postings. It does not certify Exness ingestion, historical/broker precision, large-data SLO, margin/liquidity/slippage/latency or public data rights. Ambiguity stays explicit. R0 was not explicitly pinned in the reviewed schema, so R is unavailable; MAE/MFE and Monte Carlo are not computed/accepted. V2.2 requires separate scope/authorization; the single roadmap remains [ROADMAP](docs/ROADMAP.md).
