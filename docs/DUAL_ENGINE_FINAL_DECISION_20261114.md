# Dual Engine Challenge V1: audit VPS + repo dan keputusan jalur (Claude side), 2026-11-14

Branch `claude/dual-engine-v1-20261114`, baseline bersama PR #55 head `f941eba`. Semua angka SINTETIS kecuali yang ditandai data EURUSD nyata (hak UNKNOWN, QA privat saja). Rincian ukur: `docs/benchmarks/CLAUDE_VPS_MEASUREMENTS_2026-11-14.md` (bagian A-J) dan raw evidence di `docs/benchmarks/`.

## 1. Keputusan
**Jalur COMBINE (hibrida).** Stack produk yang sudah terintegrasi (auth, antrean PostgreSQL tahan lama, worker native, Monthly Parquet kanonik, reducer finansial, jurnal) TETAP menjadi otoritas eksekusi dan finansial. Dari sisi Claude diadopsi hanya yang terbukti dan tidak mengubah otoritas finansial.

| Komponen | Keputusan | Dasar bukti |
|---|---|---|
| Reducer finansial kanonik, antrean, worker, auth, jurnal (baseline) | KEEP | Journey penuh lolos di PostgreSQL 17; 10 trader browser bersih 3/3; 15 serentak bersih 3/3; 100 trader selesai dengan klien sabar |
| Oracle OHLC independen + golden tests | ADOPT (hakim bersama) | Mesin sama dengan oracle di G0-G5; objek v2 sama dengan v1 |
| Mesin OHLC sembilan timeframe (MID per tick, int64 eksak, objek immutable) | ADOPT | G4 0,29 s, G6 3,1 s; identik dengan oracle |
| Layanan chart cursor-bound (5.000 candle per timeframe) | ADOPT dengan syarat | Prototipe lolos 9 timeframe >= 5.000 candle; belum memakai auth produk |
| Compact tick v2 (turunan non-otoritatif) | ADOPT untuk penyimpanan VPS | 5,5x lebih kecil, identik tick demi tick, OHLC byte-identik |
| Receiver/verify ingest (`ingest_incoming.py`) | ADOPT | 34/34 bulan EURUSD v1 dan 3/3 v2 lolos; deteksi file rusak teruji |
| Mesin jump finansial Claude (`claude_session.py`) | REQUIRES PARITY (belum untuk settlement) | Paritas di sintetis dan irisan nyata kecil; aktivitas nyata baru 3 event/1 fill, order jadi UNRESOLVED (belum didiagnosis) |
| Adapter R2 | REQUIRES TEST | Hanya simulasi lokal; kunci R2 belum ada |
| Frontend hybrid (busy-retry, pemulihan job terpangkas) | BUILD | Lihat bagian 4 |

Jalur yang ditolak: (a) Claude-only: tidak ada integrasi PostgreSQL/worker/auth dan mesin finansialnya belum teruji pada aktivitas nyata. (b) Codex-only: tidak ada OHLC sembilan timeframe/5.000 candle di baseline, dan kode Codex terbaru (`7c78062`, 45 commit di depan) tidak tersedia di VPS, jadi perbandingan langsung NOT COMPARABLE; keputusan ini tidak mengklaim keunggulan atas Codex terbaru.

## 2. Audit VPS (riksora_vps1)
- Host: 6 vCPU AMD EPYC, 15,6 GiB RAM, tanpa swap, disk 197 GB (15 GB terpakai), Ubuntu 24.04, kernel 6.8, tanpa sudo.
- Toolchain user-space: Python 3.13.18, NumPy 2.5.4, PyArrow 26.0.0, PostgreSQL 17.12 (micromamba), Node 22.23.5.
- Port: hanya SSH (22) yang terbuka ke luar; PostgreSQL 54329 dan API QA 8001 hanya di loopback. Firewall tidak bisa diperiksa tanpa sudo.
- Sesi lain aktif: login `developer` dari <client-ip-redacted> sejak 17:49 mengubah `fin_parity_v2.py` (argumen offset) dan menjalankan `~/bench/finreal/run2.sh`. Tidak disentuh; harus dikoordinasikan agar tidak berebut CPU saat pengukuran.
- Sisa yang dibereskan: 5 proses `qa_extra_api.py` yatim (uji multi-proses) dimatikan; penyebabnya diperbaiki (proses keluar bila induk mati). Masih ada: PostgreSQL QA 54329 dan `local_stack.py api` (8001) dari bring-up awal (boleh dimatikan atas izin).
- Disk: `~/bench` 583 MB, `~/data` 831 MB (34 bulan EURUSD v1 + 3 bulan v2), `~/tools` 948 MB, `frontend/tests/artifacts` 77 MB (281 folder bukti, di-ignore Git).
- Perlu perhatian: tidak ada kredensial GitHub di VPS (16 commit belum di-push).

## 3. Audit repo
- Cabang `claude/dual-engine-v1-20261114`, 42 commit sejak baseline (16 belum di-push), satu file berubah oleh sesi lain.
- 1.146 file berbeda dari baseline: 963 adalah penghapusan chunk candle XAUUSD (commit laptop `bd45396`), sisanya dokumen/bukti, tool Claude, dan hook QA.
- Kode produk yang disentuh sejak baseline: `execution/claude_ohlc_seam.py` + 6 baris hook di `observed_research.py` (opt-in lewat `BTL_CLAUDE_OHLC_ROOT`, reversibel, tes lolos); `execution/historical.py` (default zlib-1 untuk log Session BARU, commit laptop `1acb1d2`, perlu ditinjau pemilik); `market_data/compact_tick.py` (+362 baris jalur turunan, laptop `b731416`). Kontrak beku, `nodeBudget`, batas antrean/TTL/retensi tidak diubah.
- Hook QA opt-in di `frontend/tests/` (perekam API journey, gerbang mode anggaran, worker 3-4 dan kohort lebih besar di harness); gerbang default tidak diubah.
- Tidak ada data pasar mentah, kunci, atau token di Git (pemindaian baris tambahan bersih; folder bukti di-ignore).

## 4. Yang harus diubah agar kapasitas nyata tercapai
Kapasitas yang boleh diklaim hari ini (sintetis, fixture replay 2.048 tick): 10 trader browser aktif bersih; 15 trader serentak bersih (driver HTTP, kebijakan frontend); sampai 100 trader selesai pada anggaran 5 vCPU/14 GiB HANYA dengan klien yang sabar dan memulihkan job terpangkas. Dengan frontend sekarang, burst besar menampilkan error (batas retry 8 untuk SERVICE_BUSY, tidak ada pemulihan `poll:404`). Pembatas terukur: bukan RAM (0,9 GiB dari 14), melainkan 4 slot worker + batas antrean 16 + CPU 5 core pada 100 trader (4,7 dari 5 core), dan aturan retensi 15 job selesai (`cloud/queue.py:245`).

## 5. Keputusan yang butuh persetujuan owner (kontrak beku)
1. Ubah `BTL-PAST-CHART-CONTEXT-1` (sekarang bulan sebelumnya, halaman 512) menjadi paging sampai 5.000 candle per timeframe.
2. Retensi job selesai: naikkan `RETAINED_LIMIT`, atau terima pemulihan di sisi frontend saja.
3. Izin menurunkan/menambah batas antrean (16/2) hanya bila diinginkan; saat ini tidak diubah.
4. Kredensial GitHub dan (nanti) kunci R2 disuntik owner di VPS, tidak lewat chat.

## 6. Urutan kerja (P0)
1. Replay Session sebulan penuh (EURUSD nyata lewat alur ingest produk, QA privat) untuk mengukur RSS dan CPU per worker nyata; ini yang menentukan anggaran RAM dan kapasitas sebenarnya.
2. Diagnosis kenapa irisan nyata menjadi UNRESOLVED, lalu ulang paritas mesin jump dengan aktivitas tinggi (v1 dan v2).
3. Hubungkan layanan chart ke identitas produk, katalog lintas dataset per pair-bulan, cache SSD objek OHLC; importer OHLC M1 BID prasejarah (menunggu format dari laptop).
4. Pemulihan klien di frontend (retry busy, job terpangkas) setelah izin kontrak.
5. Push ke GitHub, pembersihan sisa VPS, uji R2 sungguhan.
