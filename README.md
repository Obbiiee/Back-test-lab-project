# Backtest Lab

Aplikasi utama: React 19, Vite 8, TradingView Lightweight Charts 5.2.1.
Satu entrypoint: `frontend/index.html` → `frontend/src/main.jsx` → `FigmaWorkspace.jsx`.
Source produksi tetap di `frontend/src/`; backend tidak diperlukan untuk workspace ini.

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
- `backend/`, `data/`: alur backend/sample terpisah; tidak dipakai entrypoint utama.
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
