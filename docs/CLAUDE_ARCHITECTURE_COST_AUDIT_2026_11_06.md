# Audit arsitektur RIKSORA: murah, cepat, efisien (2026-11-06)

> **Status:** advisory input diminta owner (Obi), ditulis Claude setelah membaca `main` @ `8ba3489`, PR terbuka #16–#41, branch `codex/parquet-one-day-duckdb-20261105`, `codex/p0-local-integration-20261106`, `codex/beta-rc-20261028`, dan file kritik `docs/CLAUDE_AUDIT_2026_11_05.md`.
> File ini **bukan** otoritas arsitektur baru dan tidak mengotorisasi apa pun. Codex pemilik backend: semua perubahan backend di bawah adalah **usulan**. Untuk tiap poin, Codex diminta memberi verdict ACCEPT / NEEDS-CHANGE / REJECT dengan bukti, lalu owner memutuskan.
> Versi dokumen hidup (bisa dikomentari): https://claude.ai/artifact/3q6ukMGuZ9cfcYqFEsbp2K

Intinya: masalah kecepatan bukan di format penyimpanan, tapi di cara server memproses setiap tick satu per satu sambil menulis bukti ke database. Ubah replay jadi "lompat ke kejadian berikutnya" (vectorized), simpan tick sebagai Parquet ramping, sajikan candle sebagai file statis, dan simpan trade di PostgreSQL saja. Hasilnya tetap satu VPS yang sekarang, biaya tambahan hampir nol.

## 1. Kondisi repo dan rencana kerja sekarang

Repo sehat secara konsep (engine tick, ledger Decimal, PostgreSQL), tapi pekerjaannya tersebar dan prosesnya sangat berat dokumen. Ini yang paling memperlambat dan memboroskan biaya, lebih dari teknologi apa pun.

| Temuan | Bukti | Dampak |
| --- | --- | --- |
| Ada beberapa jalur backend yang terpisah | `main` (8ba3489, 4 Nov) punya 77 file backend; `codex/beta-rc-20261028` punya 111 file plus `deploy/vps` (compose, Caddyfile) dan Midtrans; `codex/functional-staging-foundations` yang dulu dipakai di VPS; branch CP6A-10 lagi | Tidak jelas mana yang "produk". Tiap fitur harus diporting ke beberapa jalur |
| 9 PR terbuka, sekitar 38 branch | #16, #17, #18 (beta, sejak 24 Okt), #20 (desain), #36, #38, #39 (frontend), #40 (dokumen), #41 (integrasi P0, 6 Nov) | PR menumpuk saling bertingkat; merge makin mahal tiap hari |
| Dokumen otoritas sangat besar | `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` 470 KB, `AI_HANDOFF.md` 405 KB, `AI_CONTEXT/` sekitar 220 KB. Kode Python produksi di main hanya sekitar 9.600 baris | Setiap sesi AI menghabiskan token untuk membaca aturan, bukan menulis kode |
| Gate uji makin panjang | CP6A-10 butuh benchmark sehari penuh (5 kasus, sekitar 11 menit per kasus) hanya untuk membandingkan format baca | Kemajuan per minggu kecil, tagihan langganan AI besar |
| Disk VPS menipis | Proposal PR #40 mencatat sisa 36,47 GiB dengan batas minimum 32 GiB (24 Okt masih sekitar 163 GB). Arsip XAU kanonik sendiri 22,9 GB untuk 1 tahun 1 instrumen | Uji berikutnya bisa terhenti karena disk |
| Data harga masih di repo publik | `frontend/public/market/` 270 MB di `main` | Risiko lisensi HistData dan clone/deploy lambat |
| Keputusan owner belum tercermin | 24 Okt owner mengizinkan trading pada bulan HistData yang lolos validasi sebagai beta gratis. PR #41 masih menolak semua sesi historis: hak sumber UNKNOWN / NOT_GRANTED | Produk belum bisa dipakai dengan data 16 pair walau sudah diputuskan |

Rencana kerja yang ada (PR #20 P0–P11, CP6A, benchmark gate C0–C7) benar arahnya, tapi urutannya mengukur dulu hal yang jawabannya sudah jelas. Saran di bagian 7 memangkasnya.

## 2. Audit file kritik Claude

File kritik ada di branch `docs/claude-audit-20261105`, file `docs/CLAUDE_AUDIT_2026_11_05.md` (belum di-merge). Codex menanggapinya di PR #40. Arah kritik itu benar, tapi ada dua angka yang perlu dikoreksi setelah Codex mengukur.

| Poin kritik | Status sekarang | Koreksi atau catatan |
| --- | --- | --- |
| 2.1 Ganti store tick JSON+SHA-256 per event dengan Parquet | Benar soal ukuran, salah soal kecepatan | Codex mengukur: ganti SQLite ke Parquet/DuckDB hanya mempercepat 1–8% end-to-end (712 s vs 651–672 s untuk 1 hari XAU). Pembacaan bukan penyebab lambat |
| Perkiraan Parquet 5–15 B/quote | Sebagian meleset | Skema Codex menghasilkan sekitar 69 B per grup (9,44 MB untuk 137.108 grup) karena kolom tambahan. Skema ramping di uji Claude: 3,8–8,2 B/tick (data sintetis) |
| 2.2 Jump 72 jam secara vectorized | Benar, dan ini yang terpenting | Codex menandainya "research candidate". Laju terukur sekarang sekitar 200 grup/detik, lebih lambat dari 565/detik yang dikutip dulu |
| 2.3 Candle di repo publik | Masih terjadi | 270 MB masih di `main` |
| 3.1 Diet dokumen | Belum dikerjakan | Dokumen terus bertambah sejak 5 Nov |
| 3.3 / 3.5 Tidak ada CI dan resep deploy | Setengah benar | Resep deploy ada (`deploy/vps/compose.yaml`, Caddyfile) tapi hanya di branch beta, bukan di `main`. CI masih belum ada |
| 4.1 Hak data pasar | Belum selesai | Masih blocker untuk jualan. Untuk beta gratis, keputusan owner 24 Okt sudah ada |

Tanggapan Codex di PR #40 masuk akal untuk semua poin kecuali satu. Codex menolak "identitas per file/row group menggantikan hash per event" karena khawatir bukti forensik melemah. Jalan tengahnya: identitas event tetap ada tapi dihitung, bukan disimpan, yaitu `(datasetVersion, file, row)`. Hash SHA-256 per row group di manifest membuktikan setiap baris tidak berubah. Buktinya setara, tanpa tabel identitas yang memakan sekitar 345 B per quote.

## 3. Masalah inti: replay memproses setiap tick lewat jalur yang mahal

Satu hari XAU berisi 137.108 grup timestamp dan butuh sekitar 11 menit (sekitar 200 grup per detik, CPU 96–97% satu core). Codex sendiri mencatat waktunya habis di controller, penulisan PostgreSQL dan verifikasi, bukan di pembacaan data. Proyeksi Codex untuk 1 tahun: 44–98 jam.

Penyebabnya terlihat di kode: tiap grup tick melewati `json.dumps`, hash, `INSERT` ke SQLite timeline (`backend/ticks/timeline_v2.py`), lalu tiap 256 grup menjadi satu perintah ADVANCE yang menulis event dan checkpoint penuh ke PostgreSQL (`backend/execution/postgres.py`). Satu ADVANCE butuh sekitar 590 ms, atau sekitar 2,3 ms per grup.

| Cara memproses Jump 72 jam (sekitar 324 ribu tick) | Waktu | Sumber |
| --- | --- | --- |
| Jalur sekarang (sekitar 200 grup/detik) | sekitar 27–33 menit per klik | Hitungan dari laporan CP6A-10 |
| Loop Python biasa dengan Decimal, tanpa tulis DB | sekitar 4 detik | Uji Claude, data sintetis |
| Baca Parquet + cari trigger vectorized (NumPy), 20 order | sekitar 0,04 detik (21 ms baca + 17 ms cari) | Uji Claude, data sintetis |

Jadi jalur sekarang sekitar 400 kali lebih lambat dari loop Python polos, dan sekitar 40.000 kali lebih lambat dari cara vectorized. Uangnya berubah hanya saat harga menyentuh entry, SL atau TP. Selain momen itu server tidak perlu memproses tick satu per satu.

Uji Parquet Claude memakai 3 juta tick sintetis mirip EURUSD (timestamp ns, bid/ask integer 5 digit). Hasil: 8,2 B/tick dengan ZSTD biasa, 3,8 B/tick dengan delta encoding, dibanding CSV sekitar 30 B/tick. Data asli biasanya lebih sulit dikompres, jadi anggap 2 kali lipat. Angka ini estimasi, bukan acceptance; Codex perlu mengukur ulang di data asli.

## 4. Arsitektur data pasar yang disarankan

Prinsipnya: data pasar diproses sekali saat impor, disimpan satu kali untuk semua user, dan server hanya bekerja keras saat uang bisa berubah.

**Impor (sekali per file bulan HistData)**

1. File tick bulanan HistData masuk ke validator yang sudah ada (`precision/histdata.py`, admission). Bulan yang ditolak tetap ditolak, tanpa perbaikan atau pengurutan ulang.
2. Tulis satu Parquet per `pair/tahun/bulan`: `ts_ns` int64, `bid` dan `ask` integer (harga × 10^digit, digit dicatat di manifest), urutan baris sama persis dengan file sumber. Nomor baris menjadi `source_ordinal`, jadi tidak perlu disimpan. ZSTD level 3 + delta encoding, row group sekitar 128 ribu baris.
3. Tulis manifest JSON per bulan: `datasetVersion`, SHA-256 per file dan per row group, min/max `ts_ns` per row group, daftar gap, kelas hak data. Ini menggantikan tabel identitas per event.
4. Turunkan candle M1 (bid dan ask) sekali, simpan sebagai Parquet kecil per pair/bulan. Timeframe lebih besar dihitung dari M1 di browser atau dicache per `datasetVersion`.

**Menyajikan chart tanpa membocorkan masa depan**

- Hari yang sudah lewat dari kursor sesi bersifat tetap. Sajikan sebagai file per hari yang boleh dicache permanen (`Cache-Control: immutable`) lewat Caddy, opsional Cloudflare gratis di depannya.
- Hari berjalan disajikan API yang memotong data tepat di kursor. PyArrow membaca satu row group dalam milidetik, jadi ini murah.
- Aturan causal RevealedView di `AGENTS.md` tetap terjaga, karena browser tidak pernah menerima tick di depan kursor.

**Eksekusi: lompat ke kejadian berikutnya**

1. ADVANCE sampai waktu T: baca array `[kursor, T]` dari Parquet dengan melewati row group yang tidak relevan.
2. Untuk tiap order pending, SL dan TP, cari indeks sentuhan pertama secara vectorized di sisi harga yang benar (beli pakai ask, jual pakai bid). Gap data juga dicari vectorized (selisih `ts_ns` di atas ambang).
3. Kalau tidak ada sentuhan atau gap, kursor pindah ke T dengan satu commit kecil.
4. Kalau ada, hanya grup timestamp itu yang masuk ke reducer Decimal yang sudah ada (`execution/engine.py`). Aturan UNRESOLVED dan grup timestamp kembar tetap ditangani reducer. Commit, hitung ulang trigger, ulangi.
5. Tes emas: untuk ratusan jendela acak, hasil Jump (event, hash ledger, kursor) harus sama persis dengan replay tick per tick yang lama.

Ini sama dengan usulan "browser plays, server settles" (handoff 23 Okt) dan mode shared-source CP6A-9 yang sudah terbukti memangkas timeline per sesi 99,5%.

**Perkiraan ukuran 16 pair × 11 bulan (Nov 2024–Sep 2025)**: jumlah tick per bulan belum diukur. Dengan asumsi 1–4 juta tick per pair per bulan dan 4–8 B/tick, totalnya sekitar 0,7–6 GB, paling banyak sekitar 12 GB dengan margin 2 kali. Bandingkan dengan arsip kanonik sekarang: 22,9 GB untuk XAU 1 tahun saja. File ZIP asli disimpan di luar VPS (Backblaze B2 atau Cloudflare R2), bukan di disk VPS.

## 5. Cara menyimpan data trade trader

Tetap PostgreSQL saja, tanpa database tambahan. Yang diubah: simpan hanya hal yang berubah saat uang bergerak, dan jangan simpan apa pun per tick.

Sekarang setiap perintah menulis hasil lengkap (termasuk payload replay) ke `tick_commands`, event ke `tick_events`, dan snapshot penuh ke `tick_checkpoints`. Eksperimen QA-v3 Codex (CP6A-5) sudah membuktikan format ringkas memangkas pertumbuhan database 50,2% dengan hash hasil yang identik.

| Tabel | Isi | Cara tulis |
| --- | --- | --- |
| `sessions` | Satu baris per sesi: kursor, saldo, order dan posisi terbuka (JSONB), revision, hash ujung ledger | UPDATE di tempat, dalam transaksi yang sama dengan event |
| `session_commands` | Kunci idempotensi, hash perintah, receipt ringkas (hash hasil + respons kecil), revision | Append-only. Ini yang dipakai PR #41 untuk cek "order tersimpan atau tidak" |
| `financial_events` | Order dibuat, terisi, dibatalkan, ditutup, perubahan kas, dengan rantai hash per perintah | Append-only, hanya saat uang bergerak |
| `trades` | Satu baris per trade tertutup: waktu dan harga masuk/keluar, lot, P&L, R, Method, tag | Diturunkan dari event di transaksi yang sama. Dipakai analitik dan jurnal |
| `checkpoints` | Snapshot state penuh | Tiap N perintah (misal 50) dan di titik fork, bukan tiap perintah |
| `drawings`, `journal_entries` | Gambar chart dan catatan jurnal (JSONB) | Terpisah dari data keuangan |

Perkiraan ukuran (estimasi, belum diukur): sekitar 4 event per trade dan sekitar 2 KB per trade termasuk index. 1.000 trader × 500 trade = 500 ribu trade, sekitar 1 GB. Statistik (win rate, expectancy, drawdown) cukup query SQL ke tabel `trades` dengan index `(user_id, method_id, closed_at)`.

Backup: `pg_dump` terkompresi tiap malam plus arsip WAL dengan pgBackRest atau WAL-G ke Backblaze B2 atau Cloudflare R2. Untuk ukuran ini biayanya di bawah 1 dolar per bulan.

## 6. Teknologi open-source yang dipakai ulang

Semua yang disarankan gratis dan berlisensi aman untuk SaaS komersial. Tidak perlu server atau database baru. Lisensi baris bertanda * dicek lewat GitHub API pada 5 Nov (kritik Claude), sisanya perlu dicek ulang sebelum dipasang.

| Proyek | Lisensi | Dipakai untuk | Keputusan |
| --- | --- | --- | --- |
| Apache Arrow / PyArrow + Parquet* | Apache-2.0 | Format tick dan candle, pembacaan dengan lewati row group | Pakai sekarang (Codex sudah punya adapter di CP6A-10) |
| NumPy | BSD-3 | Pencarian trigger vectorized | Pakai sekarang |
| DuckDB* | MIT | QA dan analitik ad hoc atas file Parquet yang sama | Pakai untuk tooling saja |
| Polars* | MIT | Agregasi candle, statistik | Opsional |
| TradingView Lightweight Charts* | Apache-2.0 | Chart (sudah dipakai) | Pertahankan, wajib atribusi |
| Caddy | Apache-2.0 | HTTPS dan file statis immutable (sudah dipakai di VPS) | Pertahankan |
| pgBackRest / WAL-G | MIT / Apache-2.0 | Backup PostgreSQL ke B2/R2 | Pilih satu |
| nautilus_trader* | LGPL-3.0 | Contoh skema QuoteTick integer di Parquet dan backtest streaming | Referensi desain, jangan ganti reducer sendiri |
| hftbacktest* | MIT | Contoh loop tick cepat atas array NumPy | Referensi |
| dukascopy-node* | MIT | Unduh data dev/QA 16 pair | Hanya untuk dev, bukan data jualan |
| backtesting.py* | AGPL-3.0 | — | Hindari (kewajiban AGPL untuk SaaS) |
| vectorbt* | Apache-2.0 + Commons Clause | — | Hindari untuk komersial |

Yang sengaja tidak disarankan: TimescaleDB, QuestDB, ClickHouse untuk tick. Data historis tidak berubah dan dibaca per rentang waktu, jadi file Parquet di SSD lebih murah dan lebih sederhana daripada server database tambahan.

## 7. Urutan kerja dan keputusan owner

Semua perubahan backend di bawah ini adalah usulan untuk Codex, karena Codex pemilik backend. Gate kebenaran tetap ketat (hash emas, tanpa look-ahead, idempotensi, cold resume). Yang dipangkas hanya sweep eksplorasi (kombinasi codec × row group, run ABBA, partisi harian vs bulanan), cukup ukur sekali setelah jadi.

1. **Satukan backend.** Pilih satu jalur produk, merge, lalu tambah CI GitHub Actions (tes backend + PostgreSQL service + lint/build frontend). Branch lain di-merge atau ditutup.
2. **Impor Parquet ramping** untuk 16 pair × 11 bulan dari adapter CP6A-10 yang sudah ada, plus manifest dan tes paritas terhadap store lama.
3. **Jump vectorized** di server dengan tes emas terhadap replay tick per tick. Ini yang mengubah 30 menit menjadi kurang dari 1 detik.
4. **Candle per hari** dari Parquet: file immutable untuk hari lewat, API terpotong kursor untuk hari berjalan. Sisi frontend bisa dikerjakan Claude.
5. **Receipt ringkas + tabel `trades`**: jadikan format QA-v3 sebagai format produksi, checkpoint tiap N perintah.
6. **Uji beban** 10, 50, 100 user simulasi di VPS sekarang. Target: 100 user dengan RAM di bawah 85%.

Keputusan yang hanya bisa diambil owner:

- [ ] Jalur backend mana yang jadi produk (`main` + P0 atau `codex/beta-rc-20261028`)
- [ ] Tegaskan lagi ke Codex: bulan HistData yang lolos validasi boleh dipakai beta gratis (keputusan 24 Okt). PR #41 masih menolak semua sesi historis
- [ ] Setujui pemangkasan gate eksplorasi di atas
- [ ] Jadikan repo private dan keluarkan 270 MB data harga dari `frontend/public/market/`
- [ ] Pindahkan bukti QA lama di VPS ke B2/R2 supaya disk lega (sisa sekitar 36 GiB)
- [ ] Lisensi data sebelum mulai jualan (masih blocker, tidak bisa diselesaikan dengan kode)

## 8. Permintaan untuk Codex

1. Baca file ini, `AGENTS.md`, `AI_CONTEXT/04_CURRENT_PHASE.md`, dan PR #40.
2. Beri verdict satu baris ACCEPT / NEEDS-CHANGE / REJECT untuk bagian 2 (jalan tengah identitas event), 3, 4, 5 dan urutan kerja bagian 7, dengan bukti kode atau pengukuran.
3. Jangan mulai implementasi sebelum owner mengonfirmasi daftar verdict.

## Sumber

Semua dibaca pada 6 Nov 2026 dari repo ini.

- Kritik Claude: [docs/CLAUDE_AUDIT_2026_11_05.md](https://github.com/Obbiiee/Back-test-lab-project/blob/docs/claude-audit-20261105/docs/CLAUDE_AUDIT_2026_11_05.md)
- Tanggapan Codex: [PR #40](https://github.com/Obbiiee/Back-test-lab-project/pull/40), [SESSION_STORAGE_EFFICIENCY_PROPOSAL_2026_11_05.md](https://github.com/Obbiiee/Back-test-lab-project/blob/docs/session-storage-efficiency-20261105/docs/SESSION_STORAGE_EFFICIENCY_PROPOSAL_2026_11_05.md)
- Benchmark satu hari Parquet/DuckDB: [CP6A-10 report](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/parquet-one-day-duckdb-20261105/docs/acceptance/CP6A-10-one-day-parquet-duckdb-report.md)
- Shared source: [CP6A-9 report](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/parquet-one-day-duckdb-20261105/docs/acceptance/CP6A-9-shared-source-report.md)
- Penyimpanan ringkas: [CP6A-5 report](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/parquet-one-day-duckdb-20261105/docs/CP6A5_COMPACT_STORAGE_PERFORMANCE_2026-10-31.md)
- PR terbuka: #41, #39, #36, #20, #16–#18, #38
- Kode: `backend/ticks/timeline_v2.py`, `backend/execution/postgres.py`, `backend/execution/engine.py` di branch `codex/p0-local-integration-20261106`
- Uji Parquet Claude: 3 juta tick sintetis, PyArrow, di sandbox Claude (bukan data asli, bukan VPS)
