# RIKSORA — Synthetic Tick Data: Requirements & Acceptance V1

**Status:** PROPOSED / SPEC ONLY — bukan bukti dataset sudah PASS, bukan izin produksi.  
**Owner:** RIKSORA. **Implementer:** Claude (design/model/generator), mengikuti review code dan otorisasi pemilik repo.  
**Prioritas:** mulai **XAUUSD**, rancang extensible untuk 16 instrumen.  
**Tujuan:** membuat **feed tick sintetis baru** dari pembelajaran beberapa feed asli yang **perbedaannya masih wajar terhadap variasi antarsumber asli**, kemudian menguji kecocokannya untuk *synthetic backtest* dan *stress testing*.  
**Non-goal:** mengklaim tick sintetis merupakan harga historis broker tertentu, menggantikan bukti transaksi riil, atau membuka data sumber berlisensi.

## 0. Status, scope, dan guardrail repository

- Dokumen ini adalah **kontrak acceptance usulan**, bukan perubahan status resmi. Sebelum implementasi baca: `AI_CONTEXT/00_START_HERE.md`, `01_PROJECT_STATE.md`, `02_ARCHITECTURE.md`, `04_CURRENT_PHASE.md`, `05_PROTECTED_SYSTEMS.md`, `06_WORKFLOW_RULES.md`, `07_TEST_COMMANDS.md`, dan pemilik kontrak Parquet/Session terkini di branch kerja yang dipakai.
- **Jangan** mengubah kernel/reducer finansial, receipt, Journal, replay causal/order lifecycle, migration database, state produksi, atau Annual PASS hanya untuk membuat generator lolos.
- Generator + validator dibuat **terpisah** dari engine backtest. Format keluaran harus mengikuti **canonical tick schema dan Monthly Parquet provider yang memang berlaku di branch target**; jangan menciptakan format canonical paralel.
- Data sumber tetap privat dan di luar Git, frontend/public, log, contoh, artifact, serta PR. Publikasikan hanya metadata/evidence yang aman.
- Scope pertama: generator/validator offline, small sample, deterministic seed, tanpa download data eksternal otomatis, tanpa benchmark berat, tanpa deployment/merchant/aktivasi produksi.
- **Dataset V0 yang dibuat dari parameter manual belum tervalidasi** dan tidak boleh dipakai sebagai bukti PASS.

## 1. Dua mode yang WAJIB dipisahkan

1. **HISTORICAL_LIKE_SYNTHETIC**: mempertahankan kalender, urutan regime dan jangkar level pasar dari periode asli *yang memang diizinkan*, sambil menghasilkan quote/temporal microstructure baru secara kausal. Bukan price history aktual. Evaluasi selisih harga dapat dilakukan pada timestamp yang disejajarkan.
2. **FULLY_SYNTHETIC**: membuat jalur harga/skenario baru berdasarkan distribusi, regime dan dependensi yang dipelajari. Tidak boleh diminta sama dengan harga aktual pada timestamp yang sama. Evaluasinya secara statistik, ekonomi, dan stress, bukan pointwise price error.

Setiap artefak harus menyimpan `mode`; hasil kedua mode **tidak** boleh digabung menjadi satu klaim kualitas.

## 2. Gate G0 — Izin, provenance, dan pembatasan publikasi (HARD BLOCK)

Sebelum data suatu provider diproses untuk training, operator wajib mencatat:
- identitas provider, simbol, timezone, quote convention, rentang waktu, cara akses, checksum berkas, version/unduh, hak akses;
- bukti/ketentuan **yang benar-benar membolehkan** preprocessing, model training, derived/synthetic output, publikasi layanan, dan penggunaan komersial yang direncanakan; jika tidak jelas: `RIGHTS_UNRESOLVED`;
- aturan privasi, retensi, dan output traceability. Data sumber yang tidak memenuhi G0 tidak boleh masuk pipeline komersial.

**Jangan menganggap** bahwa mencampur data, menambah noise, tidak menjual raw tick, atau mengubahnya menjadi dataset sintetis otomatis meniadakan pembatasan lisensi. Jika izin belum jelas, data itu boleh dievaluasi hanya sejauh syarat yang berlaku mengizinkan, dan **tidak** dipakai untuk output komersial.

## 3. Spesifikasi data dan normalisasi multisumber

- Terima hanya record sumber yang benar formatnya: `timestamp_utc`, `bid`, `ask`, identitas sumber, simbol/contract spec, tick/point size, quote precision, dan sequence bila tersedia. Mapping menuju canonical schema harus eksplisit.
- **Tidak melakukan average/mix tick mentah** sebagai generator. Model harus mempelajari harga referensi bersama **dan** variasi nyata antarsumber; jagalah karakteristik spread, quote arrival, jumps, missingness yang sah, sesi market, regime dan weekend.
- Koreksi offset waktu/DST, clock drift, clock skew dan tick alignment **sebelum** perbandingan. Perlakukan tick asynchronous dengan as-of alignment bertoleransi maksimum yang ditetapkan sebelum tes; simpan staleness/coverage dan **jangan melakukan future-lookahead**.
- Pisahkan konvensi instrumen: XAUUSD vs XAUUSDm, digits, tick size, kontrak, bid/ask, nominal currency, sesi perdagangan; jangan otomatis menggabungkan feed dengan definisi tidak sebanding.
- Hard invariants keluaran: semua nilai finite; price positif; `bid <= ask`; spread >= 0; waktu UTC valid; time+sequence monoton dalam partisi; metadata lengkap; partition/index/hash konsisten; no forward leakage.
- Record pada timestamp sama dapat sah bila urutan/sequence eksplisit. Jangan dedup secara membabi buta; aturan collision harus dibuktikan terhadap model provider/canonical schema.
- Gunakan reproducible seed dan versioned model; `input hashes + config + model version + seed` harus menghasilkan keluaran/hash identik dalam environment yang dipin.

## 4. Split evaluasi anti-leakage

Buat train, validation, dan **frozen held-out test** berupa blok waktu yang tidak overlap, termasuk purging/embargo bila ada windows/lag/fit yang tumpang tindih. Holdout harus meliputi normal market, high volatility, news shock, rollover, low liquidity, weekend reopen, missing feed.

- Minimal **3 sumber independen yang benar-benar eligible**, jika tersedia, untuk kalibrasi variasi antarsumber; angka ini target V1, bukan syarat mengarang atau mencari izin fiktif.
- Minimal satu skema **held-out provider** (uji ke sumber yang tidak ikut training), selain held-out period.
- Semua pra-pemrosesan yang belajar parameter (scaler, filtering, imputation, threshold selection) harus fit hanya pada train.
- Bekukan acceptance thresholds **sebelum** membuka held-out test. Tidak boleh mengulang tuning ke test sampai PASS; versi berikutnya membutuhkan test baru atau prosedur nested evaluation.

Jika jumlah provider/coverage tidak cukup, status `INSUFFICIENT_EVIDENCE` — **bukan PASS**.

## 5. Baseline perbedaan broker (inti kriteria user)

Tujuan bukan membuat satu garis harga hasil rata-rata semua broker, tetapi membuat **feed simulasi seperti broker alternatif** yang selisihnya **tidak lebih buruk secara material** dibanding variasi antarbroker nyata pada kondisi serupa.

Pada setiap instrumen dan strata **sesi × regime volatilitas × kondisi likuiditas × event/normal**, hitung di held-out asli:
- distribusi `abs(mid_A(t)-mid_B(t))`, offset sistematis, p50/p90/p95/p99, distribusi spread bid/ask, quote gap dan staleness;
- real-vs-real jarak distribusi return pada multi-horizon, realized volatility/vol clustering, auto-/cross-correlation, fat tails/jumps, drawdown intraday, quote-count/interarrival;
- perbandingan **biaya dan hasil eksekusi** saat order, bukan hanya keindahan chart.

**Aturan equivalence yang dipreregistrasi:** jarak synthetic-vs-real pada metrik yang relevan tidak boleh lebih buruk secara material daripada envelope *real-vs-real* yang telah diukur dalam strata sama, mempertimbangkan ketidakpastian sampling dan variasi antarsumber. Bandingkan **p95 dan p99** secara terpisah; jangan hanya rata-rata.

- Untuk `HISTORICAL_LIKE_SYNTHETIC`: tambahkan error pointwise mid-price dan quote yang disejajarkan, termasuk coverage/staleness dan kasus outlier.
- Untuk `FULLY_SYNTHETIC`: **jangan** pakai error harga pointwise sebagai gate; evaluasi distribusi/conditional behavior dan stylized facts.
- Pencocokan envelope tidak boleh dibeli dengan menghilangkan fat tails atau mengecilkan spread. Tes tambahan harus mendeteksi synthetic yang terlalu mulus/terlalu menguntungkan.
- Belum ada angka tetap dalam USD, pip, atau persen yang sah lintas waktu/regime. Claude harus menghitung **nilai toleransi, confidence interval, bootstrap/test method, dan jumlah sampel efektif** dari data valid, mengunci `acceptance_config.json`, lalu menguji blind held-out.

## 6. Gates penerimaan

| Gate | PASS V1 yang dituntut | FAIL / BLOCK |
| --- | --- | --- |
| G0 Rights & provenance | Semua sumber yang digunakan eligible, evidence terdokumentasi, publikasi/output diizinkan | RIGHTS_UNRESOLVED / prohibited |
| G1 Structural | **100% hard invariants**; deterministik dan Parquet/hash roundtrip identik | record invalid, causal leak, schema/hash mismatch |
| G2 Statistical fidelity | Distribusi return multi-horizon, volatilitas, tails, jumps, autocorrelation, regime, quote arrival sesuai real-vs-real tolerance **per strata** | synthetic oversmooth, risiko tereduksi, ketidaksesuaian material |
| G3 Cross-broker equivalence | Difference/coverage/spread/error vs holdout asli berada dalam envelope antarsumber dengan CI yang ditetapkan sebelumnya; khusus pointwise hanya historical-like | jauh di luar broker envelope atau alignment tidak sah |
| G4 Execution realism | Spread, market/pending fill assumptions, SL/TP, stop/limit triggering, gap/rollover, slippage assumption dan biaya **tidak lebih optimistis sistematis** daripada baseline | fill palsu atau hasil profit meningkat karena biaya yang diremehkan |
| G5 Strategy utility | Beragam strategi & rezim pada holdout: expectancy, profit factor, trade count, win rate, R distribution, drawdown, rank/stability dan downside risk dalam tolerance yang dipreregistrasi | ranking strategi menyesatkan atau tail loss diremehkan |
| G6 Novelty, privacy, operations | Tidak menyalin segmen panjang dari training; model/input/output traceable; reproducible; akses privat; bounded mem/disk; tanpa dampak sistem terlindungi | memorization/copying, leakage, non-repeatable, dampak produksi |

**Kebijakan keputusan:**
- `PASS_SYNTHETIC_BACKTEST`: G0–G6 PASS untuk **instrumen + mode + period + provider cohort + jenis strategi** yang spesifik, disertai batas penggunaan.
- `LIMITED_STRESS_TEST_ONLY`: G0, G1, G6 PASS; generator berguna untuk skenario stress tertentu, tetapi G2–G5 belum cukup untuk klaim fidelity backtest; label harus jelas.
- `FAIL`: gate kritis gagal dengan bukti.
- `BLOCKED_RIGHTS`, `INSUFFICIENT_EVIDENCE`, `NOT_TESTED`: tidak boleh disamakan dengan PASS.

Tidak ada satu skor agregat atau target "90% metrik PASS" yang boleh menutupi kegagalan hard gate, tail-risk, atau eksekusi.

## 7. Protokol uji dan evidence minimum

1. Sebelum generator: baseline perbedaan real-vs-real serta kualitas alignment, coverage, dan hak pakai; simpan laporan berikut code/version/config/hash.
2. Jalankan unit/property tests untuk schema, corruption/recovery, boundaries, timezones, out-of-order, weekend, high volatility, extreme spread, invalid tick, multiple quotes at same timestamp.
3. Calibrate model pada train; lock model/hyperparameters dan test plan melalui validation; jangan sentuh held-out.
4. Generate **minimal 100 independent seeded scenarios** untuk uji awal kestabilan distribusi (target per strata/instrumen sesuai resource); jika kemampuan VPS tak cukup, jalankan batch kecil lebih dulu dan nyatakan `NOT_TESTED` untuk sisanya.
5. Uji **30–50 strategi representatif** bila tersedia (trend, mean reversion, breakout, scalping, intraday, swing, SL/TP sensitivitas, pending order); strategi/parameter dibekukan sebelum held-out dan dijalankan **dengan kernel identik** pada baseline real dan synthetic.
6. Ukur per-strategy: number of trades, win rate, expectancy in R, profit factor, max drawdown, adverse/favorable excursion, stop/TP hit rates, costs, tail outcomes, rank correlation, confidence intervals. Interpretasikan ketidakpastian; jangan mewajibkan profit/trade identik.
7. Lakukan negative controls: synthetic terlalu halus, constant spread, hindsight-adjusted ticks, copied ticks, artificial reduced jumps harus **gagal gate yang sesuai**.
8. Hasilkan decision per instrumen/mode dengan reproducible evidence: `source_manifest`, `rights_manifest`, `normalization_report`, `split_manifest`, `broker_baseline`, `acceptance_config`, `model_card`, `test_report`, `reproduction_commands`, `decision.json`. Publikasikan **hanya evidence aman** tanpa raw proprietary data.
9. Integrasi pada UI/Session hanya setelah gate benar-benar lulus, dengan pilihan dan label eksplisit: **SYNTHETIC / NOT OBSERVED MARKET DATA**. Receipt/Journal tidak boleh mengklaim broker-fill historis.

**Prinsip biaya:** 1 CPU dedicated per worker bila itu adalah kebijakan deploy branch saat ini; implementasi awal offline bounded dan batch/chunk. Jangan mengklaim throughput user bersamaan sebelum load test terpisah.

## 8. Deliverables Claude dan Definition of Done

Claude diminta:
- audit branch target, kontrak canonical tick+Monthly Parquet saat ini, dan sumber yang eligible;
- susun **baseline broker differences** dan preregistrasi acceptance config;
- pilih model paling sederhana yang dapat diuji terlebih dahulu (baseline stochastic/conditional), kemudian eksperimen model generatif lebih kompleks hanya bila ada peningkatan terukur;
- implementasi terisolasi: parser/adapters → normalization → model fit → sampling → canonical Parquet writer → validation/evidence;
- automated tests, model card, provenance, reproducibility manifest, resource budget; laporan apa yang diuji/tidak;
- lakukan **small-sample smoke test dahulu**. Benchmark tahunan, semua 16 pair, concurrency, publish commercial, atau migrasi runtime tidak otomatis diotorisasi;
- jangan meminta perubahan ambang setelah melihat held-out, menyembunyikan FAIL, atau menyatakan "100% selesai" bila rights/evidence/test masih terblokir.

**DoD SPEC:** dokumen ini terdokumentasi di repo dan bisa digunakan Claude sebagai acceptance contract.  
**DoD DATA:** dataset nyata generated, hash reproducible, semua gate terkait lulus dengan bukti independen — **belum tercapai hanya dengan penulisan dokumen ini**.

## 9. Contoh decision report (ilustrasi skema, bukan hasil tes)

```json
{
  "spec_version": "RIKSORA-SYNTH-TICK-V1",
  "instrument": "XAUUSD",
  "mode": "HISTORICAL_LIKE_SYNTHETIC",
  "model_version": null,
  "input_rights": "NOT_TESTED",
  "broker_baseline": "NOT_TESTED",
  "gates": {
    "G0": "NOT_TESTED", "G1": "NOT_TESTED",
    "G2": "NOT_TESTED", "G3": "NOT_TESTED",
    "G4": "NOT_TESTED", "G5": "NOT_TESTED",
    "G6": "NOT_TESTED"
  },
  "decision": "NOT_TESTED",
  "synthetic_label_required": true,
  "evidence_paths": []
}
```

## 10. Reporting contract

Laporan Claude WAJIB menutup dengan: apa yang **dibangun**, sumber/izin yang **terverifikasi**, dataset dan checksum **yang benar-benar ada**, tes yang **benar-benar dijalankan**, PASS/FAIL/BLOCKED per gate, bukti reproducibility, keterbatasan, serta tindakan berikutnya. Jika tidak punya akses data sumber atau branch terbaru, katakan jelas; jangan mengarang keberhasilan.
