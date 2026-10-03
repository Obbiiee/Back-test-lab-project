# Backtest Lab — Idea Backlog

> Source of truth untuk ide produk/bisnis yang belum menjadi phase aktif. Ide di sini bersifat eksploratif; angka/claim perlu divalidasi sebelum dipakai sebagai product claim.

## Quantitative Trading Ecosystem — Master Plan

**Status:** Parked / strategic backlog  
**Prioritas:** Belum dinilai  
**Kandidat target:** Post-v1.0 / dievaluasi setelah core Backtest Lab stabil

### Konsep utama
Ekosistem dibangun di atas tiga tema: data science, behavioral analytics/AI, dan edukasi/transparansi industri trading. Masalah yang ingin ditangani mencakup hindsight bias pada backtesting manual, friction costs/quality of execution, serta perilaku trading yang menyimpang dari trading plan.

> Catatan validasi: klaim seperti persentase trader retail yang rugi, prevalensi model broker tertentu, probabilitas margin call/risk of ruin, dan rentang losing streak tidak dianggap fakta final sampai didukung data/model yang jelas.

### Pilar 1 — Product & Tools

#### A. Blind Backtesting & Data Science Engine
- Bar-by-bar replay tanpa look-ahead untuk mengurangi hindsight bias.
- Friction costs: spread, slippage, dan komisi.
- Monte Carlo simulation setelah sampel backtest memadai.
- Output potensial: distribusi outcome, drawdown, consecutive losses, dan risk-of-ruin berdasarkan asumsi yang eksplisit.

#### B. AI Behavioral Audit & Live Risk Guard
- Kandidat integrasi MT4/MT5/webhook untuk membaca aktivitas trading yang diizinkan user.
- Behavioral rules/alerts:
  - revenge-trading signal, misalnya entry sangat cepat setelah loss;
  - risk escalation / perubahan sizing;
  - perubahan SL/TP dibanding trading plan.
- Kandidat fitur **Trading Circuit Breaker** setelah kondisi risiko tertentu.
- Safety/product-design note: bila dikembangkan, bedakan alert/advisory dengan kontrol eksekusi. Mekanisme lockout membutuhkan desain consent, override, reliability, security, broker/API feasibility, dan fail-safe yang matang.

### Pilar 2 — Edukasi & Konten

#### A. Dapur Broker: A-Book vs B-Book
- Edukasi struktur eksekusi/order routing, liquidity provider, market making, spread, komisi, dan conflict of interest.
- Hindari menyederhanakan semua broker menjadi satu model; jelaskan hybrid execution bila relevan.
- Kandidat konten eksperimen: membandingkan spread/slippage beberapa broker saat event volatilitas tinggi seperti NFP/FOMC dengan metodologi dan disclosure yang transparan.

#### B. Law of Large Numbers & Expected Value
- Edukasi probabilistic thinking daripada mengejar win rate sempurna.
- Jelaskan hubungan sample size, variance, expected value, drawdown, dan disiplin risk management.

### Pilar 3 — Model Matematika & Probabilitas

Model dasar:
- W = win rate
- Rw = average reward
- L = loss rate = 1 − W
- Rl = average loss/risk
- C = transaction costs

Expected value perlu didefinisikan secara konsisten terhadap unit R/currency dan memasukkan friction costs.

#### Kandidat RR / Win-rate Analytics
Tabel awal yang perlu divalidasi:
- RR 1:0.5 → break-even WR 66.7%
- RR 1:1.0 → break-even WR 50.0%
- RR 1:1.5 → break-even WR 40.0%
- RR 1:2.0 → break-even WR 33.3%
- RR 1:3.0 → break-even WR 25.0%

Break-even tersebut adalah kondisi ideal sebelum biaya transaksi; friction costs akan menaikkan win rate yang dibutuhkan.

**Jangan hard-code “max consecutive loss wajar” atau “margin call mendekati 0%” sebagai hukum umum.** Keduanya bergantung pada win probability, dependence/autocorrelation, sizing, leverage, account rules, horizon, costs, dan model distribusi. Gunakan simulation/model assumptions yang transparan.

### Monetisasi — Hipotesis, bukan harga final
- B2C SaaS: Backtest Engine + behavioral analytics. Ide awal: USD 29–79/bulan.
- Private analytics / alert products. Ide awal: USD 49–99/bulan.
- Affiliate/B2B partnerships dengan disclosure conflict-of-interest yang jelas dan proses evaluasi partner.
- Semua pricing, positioning, dan partnership perlu market validation sebelum masuk roadmap aktif.

### Alur evaluasi
Idea Backlog → validasi problem & evidence → product specification → prioritas → ROADMAP → phase implementation.
