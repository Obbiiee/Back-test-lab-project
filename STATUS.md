# RIKSORA — STATUS (satu halaman kebenaran)

> Diperbarui: 2026-11-25. Halaman ini hanya merangkum. Aturan teknis/finansial tetap di `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`; izin kerja di `AGENTS.md`; alur baca di `AI_CONTEXT/00_START_HERE.md`. Bila halaman ini bertentangan dengan fakta di server, perbaiki halaman ini.

## 1. Trunk
- **Branch tunggal: `main`** (lokal). Sejak 2026-11-25 `main` = trunk produk (bekas `claude/dual-engine-v1-20261114`) dan menyertakan riwayat `main` lama lewat merge `-s ours`, jadi bisa di-push ke `origin/main` sebagai fast-forward biasa (tanpa force).
- Semua pekerjaan baru langsung di `main`; jangan membuat branch baru untuk pekerjaan rutin.
- Branch lama (`codex/*`, `claude/*` lama, `main` lama) hanya ada sebagai tag `archive/<nama>`. Belum di-port dari `main` lama: commit `0b9fbc8` (cache blok posisi di `timeline_v2.py`, optimasi performa; perlu tes engine sendiri). Lihat: `git show archive/main-20261109`.

## 2. Apa yang live di https://riksora.com (diverifikasi 2026-11-23)
| Bagian | Fakta |
|---|---|
| Landing + halaman publik | `frontend/src/site`, dibangun dan diterbitkan oleh `deploy/site/publish.sh` ke `~/site/dist`, dilayani Caddy |
| Aplikasi `/app` | Login Google; API `deploy/site/app_api.py` (127.0.0.1:8010), 3 worker native, PostgreSQL 17 (`~/prod/pg`, port 54450) |
| Kode yang berjalan | `~/releases/riksora-ec79afd` (bukan working tree) |
| Engine | Jalur single-instrument: replay tick bid/ask, reducer finansial beku, checkpoint **compact-v2**, multi-method |
| Data | HANYA sintetis: Parquet bulanan (`~/prod/data/*/monthly/YYYY-MM/ticks.parquet`) berlabel SYNTHETIC / TEST ONLY. Tidak ada data pasar |
| Pembelian Pro | Tertutup (Midtrans urusan owner) |

## 3. Yang BUKAN produk (QA saja)
- Jalur multi-pair `backend/execution/mi_*` — terisolasi, belum terhubung ke produk.
- `deploy/local/dev_stack.py` — menjalankan produk yang sama di laptop (`docs/LOCAL_RUN.md`).

## 4. Satu jalur kerja
1. Ubah kode di branch kerja → tes terarah → commit.
2. Salin ke `~/releases/riksora-<sha>` → arahkan API ke sana → smoke test.
3. Situs statis: `deploy/site/publish.sh`.
4. Tidak ada push/merge/rewrite Git tanpa persetujuan owner (owner menolak sanitasi/push, 2026-11-18).

## 5. Keputusan yang menunggu owner
- Push `main` ke GitHub (fast-forward, tanpa force). Catatan: tiga commit historis memuat nama pribadi owner (lihat `docs/acceptance/RIKSORA-GIT-AUDIT-20261118.md`); owner menolak sanitasi 2026-11-18.
- Menghapus branch remote lama (tidak bisa dibatalkan).
- Data pasar nyata (hak data UNKNOWN), pembayaran produksi, margin, aktivasi MI.
- Commercial V1 tetap **BLOCKED**.

## 6. Dokumen lama
Laporan di `docs/acceptance/` dan `docs/*` adalah bukti historis, bukan instruksi. Bila ragu, ikuti halaman ini lalu `AI_CONTEXT/04_CURRENT_PHASE.md`.
