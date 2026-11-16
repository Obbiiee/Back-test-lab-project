# RIKSORA — kapasitas ekonomis maksimum VPS1 (laporan akhir, 2026-11-16)

Status: **IMPLEMENTATION REGISTER / LAPORAN PENGUKURAN, bukan otoritas arsitektur.** Semua angka berasal dari data **sintetis**, di **satu host** (VPS1), dengan generator beban di host yang sama (cgroup dan core terpisah), lewat **HTTP loopback tanpa TLS dan tanpa reverse proxy**. Label: **MEASURED** = diukur; **ESTIMATED** = turunan matematis dengan asumsi tertulis; **UNKNOWN** = belum diukur. **Commercial V1 tetap BLOCKED**; laporan ini bukan klaim kesiapan jual dan tidak mengubah gerbang mana pun. Konfigurasi QA di bawah ini **tidak aktif di produksi** dan butuh persetujuan owner.

## 0. Jawaban ringkas (A–F)

| | Pertanyaan | Jawaban | Label |
|---|---|---|---|
| **A** | Trader aktif maksimum yang terbukti? | **75** bersamaan, sustained 15 menit, lulus semua SLO usulan (tipis: penolakan 0,90% dari batas 1%). Pada konfigurasi produk bawaan: **30** | MEASURED |
| **B** | Angka konservatif untuk Commercial V1? | **60** (sustained lulus dengan penolakan 0,07% dan latensi p95 ≤ 0,53 s; sekitar 20% di bawah titik terbukti). **Hanya bila** konfigurasi QA di bagian 5 disetujui dan diaktifkan; tanpa itu angka konservatifnya **30** | MEASURED |
| **C** | Biaya sewa per slot trader aktif per bulan (Rp270.000)? | 60 slot → **Rp4.500**; 75 slot → **Rp3.600**; 30 slot (konfigurasi bawaan) → **Rp9.000**. Hanya biaya sewa VPS | MEASURED + aritmetika |
| **D** | Pelanggan yang bisa dilayani menurut rasio peak concurrency? | Bagian 7: 60 slot → 1.200 / 600 / 300 / 120 pelanggan pada rasio 5 / 10 / 20 / 50% (75 slot: 1.500 / 750 / 375 / 150) | ESTIMATED |
| **E** | Bottleneck pertama? | Berurutan: (1) anggaran koneksi DB 12 + gerbang API 8; (2) 3 slot operasi langsung; (3) **batas antrean produk 16 / 2 per pengguna** (di 82–90 trader). CPU baru terpakai **43%** dari 5 core pada 90 trader, RAM puncak 1,9 GB | MEASURED |
| **F** | Optimasi termurah yang menaikkan kapasitas? | Bagian 5: anggaran DB 12→24 dan API 8→16 (30→60), pool koneksi (CPU turun 25–45%), pengurangan permintaan klien, 6 slot + 4 worker | MEASURED |

Tiga angka yang **tidak boleh disamakan**: **kapasitas maksimum sesaat (rush)**, **kapasitas operasional aman (sustained)**, dan **jumlah pelanggan bulanan**. Trader aktif bersamaan bukan jumlah pelanggan.

## 1. Topologi dan lingkungan
```
generator (cgroup btl-drv: 100% CPU, core 5, 2 GB)          SUT (cgroup btl-sut: 500% CPU, cores 0-4, 12 GB, tanpa swap)
  httpx asyncio, 1 akun/trader, X-Forwarded-For berbeda  ->   uvicorn/FastAPI API  ->  autentikasi/entitlement
  persona + seed + think time                                    -> antrean durable PostgreSQL (SKIP LOCKED) -> pekerja native (4 proses)
  HTTP loopback, TANPA TLS dan TANPA reverse proxy               -> mesin tick kanonik -> checkpoint/receipt -> Journal/Analytics/ekspor
```
- **VPS1:** 6 vCPU AMD EPYC (1 thread/core), 16 GB RAM, Ubuntu 24.04, kernel 6.8, disk 197 GB, tanpa swap. PostgreSQL 17 sekali pakai per stage (user-space), Python 3.13.
- **Anggaran resmi uji (disetujui owner):** SUT 5 core dan 12 GB, generator di core ke-6 dan 2 GB. Gerbang OS aktif di semua stage: MemAvailable < 1 GiB, swap, disk bebas < 30 GB, CPU host > 97% selama 10 s, OOM di cgroup SUT. **Tidak ada gerbang yang tersentuh.**
- **Batasan metode (jujur):** generator dan SUT berbagi host sehingga cache L3, bandwidth memori, dan I/O tetap dibagi; penyematan core adalah afinitas, bukan CPU eksklusif; tidak ada biaya TLS, proxy, atau jaringan nyata; satu dataset sintetis 65.536 tick dan satu profil trade; stage sustained hanya 15 menit, bukan berjam-jam. Kesehatan generator: event-loop lag p95 ≤ 2,0 ms dan CPU generator ≈ 0,08 core, jadi generator tidak jenuh.
- **Evidence:** `docs/benchmarks/vps1-capacity-2026-11-16/` (analisis tiap stage dan `tables.md`, dihasilkan skrip `make_tables.py`), harness di `backend/tools/claude_exp/stack/capacity_http*.py`.

## 2. Beban kerja dan persona
Sepuluh persona direncanakan; yang diimplementasikan dan diukur ada tujuh, dengan campuran uji awal (bukan data pelanggan): swing 20%, scalper 20%, impulsive 15%, averaging 10%, hedging 10%, multipair 15%, researcher 10%. Setiap trader menjalankan script bersifat deterministik (seed 1) berulang selama stage, dengan think time (scalper 2–6 s, swing 20–45 s, dan seterusnya), membuat akun sendiri, dan memakai order pasar, order terencana dengan stop dan target, hedging dan averaging (diterima engine), Step, Play, Jump, Journal, analitik, ekspor CSV dan PDF. **Multipair** berarti beberapa Sesi berbeda dalam satu akun pada fixture yang sama (fixture sintetis tidak punya pasangan mata uang lain). **Grafik OHLC UNSUPPORTED** pada sesi sintetis (`chart-bars` tidak dikonfigurasi): biaya chart **UNKNOWN**. Close terhadap order yang tidak ada dijawab 503 `SERVICE_UNAVAILABLE` (seharusnya 4xx; temuan pemetaan error, dihitung sebagai penolakan sah yang diharapkan).

Biaya CPU per trader aktif per persona (konfigurasi bawaan, MEASURED dari referensi idle dan durasi script nyata): scalper 0,198 core; impulsive 0,121; hedging 0,073; researcher 0,052; averaging 0,037; multipair 0,028; swing 0,023. Biaya didorong **jumlah perintah**, bukan jumlah tick: satu scalper setara sekitar 8,6 trader swing. Campuran berbobot ≈ 0,083 core (bawaan).

## 3. Kriteria (usulan, belum disetujui owner)
Lulus bila **semuanya**: paritas finansial sama dengan referensi persona yang sama pada server idle; tidak ada error atau journey gagal; p95 Journal, Analytics, summary, penerimaan Jump dan Step ≤ 2 s (usulan owner: Journal/Statistics ≤ 8 s saat berat, dilampaui dengan margin besar); queue wait p95 ≤ 5 s; penolakan admission ≤ 1% permintaan; antrean tidak tumbuh tanpa batas (semua job SUCCEEDED); generator sehat; tidak ada gerbang OS tersentuh. Standar "longgar" (dilaporkan terpisah): journey 100%, paritas, dan latensi lulus, penolakan sementara yang berhasil diretry diperbolehkan.

## 4. Hasil
### 4.1 Konfigurasi bawaan produk (3 slot, DB 12, API 8, 3 worker, 4 vCPU untuk SUT)
| Trader | Hasil tangga 3 menit | Catatan |
|---|---|---|
| 1 / 2 / 4 / 8 / 12 / 20 | lulus | CPU 0,18 → 0,88 core |
| 30 | lulus; **sustained 15 menit lulus** (145 script, paritas 145/145, penolakan 0,51%, CPU 2,13 core) | **angka terbukti bawaan** |
| 35 | lulus 3 menit; sustained gagal tipis (penolakan 1,38%) | |
| 40 | gagal tipis (1,07–2,2% antar-run) | zona kabur |
| 50 | gagal (penolakan 3,4%) | pembatas: koneksi DB dan gerbang API |

### 4.2 Matriks optimasi (tangga 3 menit, harness, workload, worker, dataset, seed identik; tabel penuh di `tables.md`)
| Eksperimen | Perubahan (di balik flag QA) | Stabil tertinggi | Catatan |
|---|---|---|---|
| m0 | baseline | 30 | gagal di 40 |
| m1 | pengurangan permintaan klien | 40 | summary dan polling berkurang |
| m2 | cache timeline 64 per worker | 30 | **tidak ada pengaruh** pada skala ini |
| m3 / m4 | **DB budget 16 / 24** | **50 / 50** | pembatas pertama terbukti: koneksi DB |
| m5 / m6 / m7 | DB+API 16+12 / **24+16+tunggu 32** / 32+24+48 | 50 / **60** / 60 | di atas 24 tidak menambah |
| m10 / m11 | m6 + 4 / 6 slot | 60 / 60 (lulus latensi, queue wait di 6 slot 5,2 s) | slot mulai jadi pembatas di ~75 |
| m8b | pool koneksi saja (setelah perbaikan) | 40 | CPU turun 25–29% |
| m12 | pool + klien + cache + DB 24 + API 16 | gagal tipis di 60 (1,01%, seluruhnya antrean 16) | CPU 1,17 core (m6: 2,08) |

**Kegagalan pool awal (m8, m9) bukan kesalahan idenya:** `cloud/queue.py` memakai kunci advisory **sesi** yang bergantung pada umur koneksi; koneksi dari pool mempertahankan kunci itu sehingga slot worker terkunci. Diperbaiki dengan dua lapis (koneksi langsung untuk jalur antrean; pool menolak menyimpan koneksi yang memegang kunci sesi). Regresi penuh dengan pool aktif: **216/216 tes lulus**, kontrol tanpa pool juga lulus.

### 4.3 Konfigurasi akhir pada anggaran resmi 6 core (SUT 5 core)
Konfigurasi: 6 slot operasi langsung, 4 worker, DB 24, API 16 (tunggu 32), pool koneksi, pengurangan permintaan klien, cache 64.

| Uji | N | Hasil | Penolakan | Queue wait p95 | p95 summary / journal / jump / step | CPU SUT | Paritas | Journey |
|---|---:|---|---:|---:|---|---:|---|---:|
| Sustained 15 menit | 60 | **LULUS penuh** | 0,07% | 1,6 s | 0,52 / 0,53 / 0,45 / 0,48 s | 2,00 core | 272/272 | 100% |
| Sustained 15 menit | **75** | **LULUS penuh** | 0,90% | 2,8 s | 0,85 / 0,96 / 1,19 / 0,84 s | 2,16 core | 308/308 | 100% |
| Sustained 15 menit | 82 | gagal hanya penolakan | 2,29% (843 `QUEUE_CAPACITY`) | 4,0 s | 1,07 / 1,00 / 1,13 / 1,43 s | 2,10 core | 309/309 | 100% |
| Sustained 15 menit | 90 | gagal hanya penolakan | 3,72% (1.440 `QUEUE_CAPACITY`) | 4,2 s | 1,16 / 0,93 / 1,59 / 1,79 s | 2,19 core | 333/333 | 100% |
| Tangga 3 menit | 100 | gagal | 6,86% | 4,7 s | 1,86 / 1,90 / 1,92 / 2,47 s | 1,81 core | 113/113 | 98,3% (2 trader gagal saat pendaftaran) |
| **Rush** (semua tiba ≤ 5 s, 2 menit) | 50 | journey 100%, penolakan 1,67% | | 1,0 s | | 0,89 core | 58/58 | 100% |
| **Rush** | 60 | journey 100%, penolakan 2,68% | | 2,0 s | | 1,02 core | 69/69 | 100% |
| **Rush** | 75 | **gagal** (6 dari 85 journey gagal: `SERVICE_BUSY` saat pendaftaran akun) | 4,57% | 2,7 s | | 1,29 core | 79/79 | **92,9%** |

Seluruh stage: **tidak ada selisih finansial** pada script yang selesai; semua job berstatus SUCCEEDED (4.097 pada sustained 75); tidak ada OOM, swap, atau gerbang OS yang tersentuh.

**Kapasitas maksimum sesaat (rush, MEASURED):** 60 trader tiba serentak (dalam 5 detik) tanpa satu journey pun gagal; 75 gagal (gelombang pendaftaran akun menabrak gerbang API). Titik antara (65–70) **tidak diukur**. **Kapasitas operasional aman (sustained, MEASURED):** 75 lulus tipis, **60 lulus dengan margin**. Pada standar longgar (journey 100%, latensi lulus) tercatat 90, tetapi dengan penolakan 3,7% yang seluruhnya diretry; itu bukan standar yang saya usulkan sebagai kapasitas aman.

### 4.4 Sumber daya pada sustained 75 trader (MEASURED)
- **CPU SUT:** 2.976 core-detik dalam 1.375 s = **2,16 core rata-rata (43% dari 5 core)**; API dan lainnya 1.057 s, worker finansial 1.285 s, PostgreSQL 397 s. CPU "tak terlacak" (proses berumur pendek, terutama backend PostgreSQL baru per koneksi) turun dari **46%** (konfigurasi bawaan) menjadi **8%** dengan pool: bukti langsung efek pool. Biaya per trader aktif ≈ **0,053 core** (bawaan: 0,07–0,08).
- **RAM:** puncak SUT 1,83 GB (API 235 MB, worker 286 MB per proses, PostgreSQL 195 MB); MemAvailable host minimum 13,0 GiB. **CPU host:** maksimum 65% (dari 6 core).
- **PostgreSQL:** koneksi aktif maksimum 39 (anggaran 24 di proses API ditambah worker); 16.680 sesi dibuka dalam 15 menit (≈ 12/s, bawaan ≈ 85–100/s); database +185 MB dan WAL +359 MB per 15 menit pada 75 trader dengan 20.703 baris checkpoint (44 MB); `max_connections` = 200.
- **Jaringan (badan HTTP saja, tanpa header dan TLS):** masuk ≈ 1,4 MB dan keluar ≈ 0,06 MB per trader per 15 menit (≈ 106 MB dan 4,5 MB total).
- **Throughput:** 28,7 permintaan/s; 458.289 tick maju, 2.484 trade tertutup, 120 Jump dalam 15 menit.
- **Fairness (MEASURED):** queue wait p50 0,26 s, p95 2,8 s, p99 5,1 s, maksimum 7,2 s; tidak ada job EXPIRED atau gagal; waktu penyelesaian script per persona stabil (swing p95 729 s, scalper 306 s, impulsive 108 s) tanpa tanda starvasi.

## 5. Optimasi dan dampaknya (semua di balik flag QA, default produk identik)
| # | Optimasi | Dampak terukur | Risiko / catatan |
|---|---|---|---|
| 1 | `BTL_DB_BUDGET` 12→24 dan `BTL_API_ADMISSION_LIMIT` 8→16 (+ tunggu 32) | **30 → 60** trader | Menyentuh batas produk; jumlah koneksi PostgreSQL harus tetap < `max_connections` |
| 2 | `BTL_DB_POOL=1` | CPU **−25 s/d −45%** pada beban sama; CPU tak terlacak 46% → 8% | Kode baru di lapisan DB; wajib regresi (216 lulus); jalur antrean memakai koneksi langsung karena kunci sesi |
| 3 | Pengurangan permintaan klien (`--client-opt`) | 30 → 40 pada baseline | Perubahan di klien/frontend; stale-revision dipulihkan dan dilaporkan |
| 4 | `BTL_DIRECT_OPERATION_CONCURRENCY` 3 → 6 dan 4 worker | memangkas queue wait dan latensi pada 60–75 trader | Hanya berguna setelah #1; sendirian memperburuk penolakan |
| 5 | `BTL_FIXTURE_CACHE_ENTRIES` 64 | **tidak ada pengaruh** pada skala ini | Tidak perlu dikejar |
| — | **Berikutnya (butuh persetujuan owner, belum diuji):** batas antrean 16 / 2 per pengguna | Pembatas di 82–90 trader; CPU masih 43% | Menyentuh batas produk TTL/admission |
Tidak ada perubahan pada algoritma finansial, reducer, receipt, atau kontrak beku. Semua perubahan memakai variabel lingkungan dengan default sama dengan produksi; semuanya **belum diaktifkan di produksi**.

## 6. Sensitivitas terhadap komposisi trader (ESTIMATED dari biaya per persona, bawaan)
Kapasitas CPU aman (65% dari 5 core ≈ 3,25 core, bawaan): semua scalper ≈ 16; campuran uji ≈ 39; semua swing ≈ 140. Dengan pool, biaya per trader turun sekitar sepertiga. Kapasitas "N trader" **bergantung komposisi**: satu scalper berat memakan jatah beberapa trader swing. Batas laju perintah per akun (keputusan produk, belum dikerjakan) melindungi dari satu pengguna berat.

## 7. Ekonomi (ESTIMATED; biaya sewa VPS Rp270.000/bulan, asumsi owner)
Biaya sewa per slot trader aktif bersamaan = Rp270.000 ÷ kapasitas.

| Kapasitas | Dasar | Biaya per slot per bulan |
|---|---|---:|
| 30 | MEASURED (bawaan, sustained) | Rp9.000 |
| 60 | MEASURED (konfigurasi QA, sustained, margin) | Rp4.500 |
| 75 | MEASURED (konfigurasi QA, sustained, tipis) | Rp3.600 |
| 10 / 20 / 50 / 100 | HYPOTHETICAL (aritmetika) | Rp27.000 / Rp13.500 / Rp5.400 / Rp2.700 |

Pelanggan berbayar yang didukung = slot ÷ rasio peak concurrency (ESTIMATED; rasio adalah asumsi, bukan data):

| Rasio peak concurrency | 5% | 10% | 20% | 50% |
|---|---:|---:|---:|---:|
| 60 slot (konservatif) | 1.200 | 600 | 300 | 120 |
| 75 slot (terbukti, tipis) | 1.500 | 750 | 375 | 150 |
| 30 slot (bawaan) | 600 | 300 | 150 | 60 |

Biaya sewa VPS per pelanggan berbayar: Rp270.000 ÷ pelanggan. Pada 600 pelanggan (60 slot, rasio 10%) ≈ **Rp450 per pelanggan per bulan**; pada harga nyata Rp87.000 per bulan itu 0,5% dari pendapatan, dan pada paket tahunan Rp400.000 (setara Rp33.333 per bulan) 1,4%. Kebutuhan VPS tambahan bila kapasitas terlampaui: satu VPS identik per kelipatan kapasitas **hanya bila batas antrean produk ikut diskalakan**; kapasitas dua VPS **tidak boleh diasumsikan** dua kali lipat (UNPROVEN). **Belum termasuk:** pengguna Free (biaya komputasi dan penyimpanannya), penyimpanan dan backup (R2 untuk data pengguna), bandwidth berbayar, biaya payment gateway (QRIS 0,7%, kartu 2,9% per halaman resmi Midtrans, ditambah PPN atas biaya), pajak, domain, biaya hukum dan akuntansi, dan waktu dukungan.

## 8. Yang tidak terbukti (UNKNOWN / UNPROVEN)
- Biaya dan latensi grafik OHLC sembilan timeframe, indikator, dan alat gambar (tidak ada di sesi sintetis).
- Jalur **TLS dan reverse proxy**, jaringan nyata, dan browser nyata (biaya CPU browser adalah biaya perangkat trader, tidak diukur).
- Beban 20, 50, atau 100 trader **di mesin generator eksternal** (hanya same-host).
- Stabilitas berjam-jam; hanya 15 menit per konfigurasi.
- Hasil pada data pasar nyata (sintetis saja) dan pada 16 instrumen.
- Skala di atas 90 trader dan kapasitas dua VPS.
- Efek konfigurasi QA pada produksi: **belum aktif dan belum disetujui**.

## 9. Rekomendasi
1. Jangan menyebut kapasitas pelanggan di luar bagian 7. Angka konservatif Commercial V1: **30** (bawaan) atau **60** (bila konfigurasi QA disetujui).
2. Putuskan standar penolakan yang layak (usulan ≤ 1%) dan apakah #1 dan #2 di bagian 5 diaktifkan di produksi; keduanya butuh uji E2E browser dengan TLS sebelum dipakai.
3. Pertimbangkan batas laju perintah per akun dan pembahasan batas antrean 16 / 2 sebagai langkah berikutnya, setelah persetujuan terpisah.
4. Pengujian generator eksternal bila VPS kedua tersedia, untuk memvalidasi biaya TLS dan jaringan.

## 10. Reproduksi
`backend/tools/claude_exp/stack/capacity_http.py` (stage), `capacity_http_driver.py` (trader), `capacity_http_analyze.py` (paritas dan kriteria); tabel dihasilkan `docs/benchmarks/vps1-capacity-2026-11-16/make_tables.py` dari 83 berkas analisis. Commit harness dan perubahan flag berada di cabang `claude/dual-engine-v1-20261114`; SHA bundle akhir dicatat di pesan penutup sesi.
