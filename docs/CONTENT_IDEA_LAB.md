# Backtest Lab — Content Idea Lab

> **Status:** Living content backlog  
> **Purpose:** Menyimpan ide konten yang lahir dari proses membangun Backtest Lab dan riset trading.  
> **Goal:** Content → Research → Experiment → Insight → Product → User Feedback → New Research/Content.

## Content Identity

Positioning: **builder + researcher**, bukan trading guru.

Core message:

> **Kalau ada klaim trading, jangan percaya dulu. Kita tes.**

Tone:
- serius tapi mudah dipahami;
- storytelling;
- evidence-first;
- transparan soal uncertainty;
- hindari flex profit sebagai fondasi kredibilitas;
- tunjukkan proses, eksperimen, kegagalan, dan perubahan pikiran ketika data berbeda.

## Content Pillars

### 1. Trading Research
Edge, expectancy, RR, sample size, drawdown, Monte Carlo, robustness, OOS, regime, execution friction.

### 2. Build in Public
Membangun Backtest Lab dari nol, keputusan UX, architecture, bugs, scaling, AI, data engineering.

### 3. Myth / Claim Testing
Ambil klaim trading populer → definisikan → uji → tunjukkan evidence dan keterbatasannya.

### 4. Risk & Uncertainty
Risk tidak menciptakan edge; survival, sequence risk, geometric growth, sizing.

### 5. Trading Reality
Spread, slippage, bid/ask, intrabar ambiguity, news, liquidity, backtest-to-live gap.

### 6. Research Psychology / Behavior
Execution drift dan behavior berdasarkan data, tanpa diagnosis psikologis.

---

# YouTube — Long Form

Target awal: mini-documentary / research story sekitar 15–35 menit jika topiknya memang membutuhkan kedalaman.

## Series: Build Backtest Lab

- Saya mencoba membangun laboratorium trading sendiri.
- Kenapa backtest biasa belum cukup?
- Dari chart replay menjadi research platform.
- Bagaimana menyimpan satu eksperimen agar bisa direplikasi?
- Kenapa AI tidak boleh menghitung statistik utama kita?
- Bagaimana website trading dipersiapkan dari 1 server sampai banyak user?
- Kesalahan arsitektur yang hampir kita buat.
- Building Monte Carlo Lab.
- Building Strategy Destruction Lab.
- Building Market Regime Lab.
- Building Experiment Passport.

## Series: Don't Trust the Claim. Test It.

- Apakah RR 1:2 otomatis lebih bagus dari 1:1?
- Apakah win rate tinggi berarti strategi bagus?
- 10 kemenangan berturut-turut: skill atau sequence?
- Berapa banyak trade yang sebenarnya kita butuhkan?
- Strategi profit 1 bulan: edge atau kebetulan?
- Apa yang terjadi kalau spread naik 2x?
- Apakah strategi tetap hidup jika entry digeser sedikit?
- Kenapa optimasi 100 parameter bisa menemukan “holy grail” palsu?
- Backtest bagus, live jelek: di mana gap-nya?

## Series: Trading Mathematics

- Break-even win rate dijelaskan tanpa matematika rumit.
- Expectancy dalam satu video.
- Profit Factor: berguna tapi tidak cukup.
- Arithmetic expectancy vs geometric growth.
- Monte Carlo untuk trader.
- Risk of ruin vs margin call.
- Maximum drawdown: historical vs future uncertainty.
- Multiple testing dan false discoveries.

## Long-Form Story Template

    Hook / claim
        ↓
    Why people believe it
        ↓
    Define the question precisely
        ↓
    Build experiment
        ↓
    Show data
        ↓
    What result says
        ↓
    What result DOES NOT say
        ↓
    Stress test / alternative explanation
        ↓
    Conclusion + next experiment

---

# Reels / Short-Form Video

Target: satu ide, satu visual, satu takeaway. Reels juga dapat dipakai ulang untuk Shorts/TikTok setelah disesuaikan.

## Hooks / Ideas

- “RR 1:2 bukan berarti win rate kamu harus 33%.”
- “Profit 20% belum membuktikan strategi punya edge.”
- “100 strategi diuji? Salah satunya bisa terlihat jenius cuma karena kebetulan.”
- “Risk management tidak menciptakan edge.”
- “Backtest kamu mungkin benar secara hitungan tapi salah secara eksekusi.”
- “Kenapa dua trader dengan strategi sama bisa punya drawdown berbeda?”
- “Max drawdown backtest bukan batas maksimum drawdown masa depan.”
- “AI jangan dipercaya menghitung ini.”
- “Satu candle kena TP dan SL. Mana yang kena dulu?”
- “Kenapa saya bikin Experiment Passport?”
- “Trading strategy saya hancurkan sendiri sebelum market yang menghancurkannya.”
- “Win rate tanpa RR hampir tidak berarti.”
- “Chart terlihat trending. Tapi bagaimana komputer mendefinisikan trend?”
- “Saya sengaja membuat strategi saya lebih jelek. Ini alasannya.”
- “Free backtest harus tetap berguna. Yang saya jual adalah deeper evidence.”

## Short Structure

    0–3s    Hook
    3–10s   Problem
    10–30s  One experiment / visual
    30–45s  Result
    45–60s  Limitation / takeaway

Exact duration follows platform/content needs.

---

# Instagram

Instagram bukan hanya tempat repost video. Gunakan format yang cocok untuk visual evidence.

## Carousel Ideas

- 7 hal yang harus disimpan setiap kali backtest.
- Win Rate vs Break-Even Win Rate.
- Historical DD vs Monte Carlo DD.
- Backtest → Robustness → OOS → Forward.
- Anatomy of an Experiment Passport.
- Kenapa 100 parameter tests berbahaya.
- 5 sumber Backtest-to-Live Gap.
- Candle mode vs tick mode.
- Apa itu Strategy Destruction Lab?
- Apa yang Free vs Pro ukur di Backtest Lab.
- “What happened?” vs “How strong is the evidence?”

## Static / Infographic

- Formula break-even WR.
- Experiment lifecycle.
- Research hierarchy.
- Market uncertainty map.
- Controllable vs uncontrollable.
- Backtest Lab architecture simplified.
- Research Integrity flow.
- Monte Carlo distribution snapshots.

## Stories

- Poll: “Menurut kamu RR 1:3 butuh WR berapa untuk BE?”
- Before/after feature build.
- Bug of the day.
- Screenshot research result.
- “Which claim should we test next?”
- Mini build log.
- Behind-the-scenes experiment.
- Q&A yang kemudian menjadi YouTube episode.

---

# Cross-Platform Content Engine

Satu riset sebaiknya menghasilkan banyak aset.

Example:

    RESEARCH QUESTION
    “Does RR 1:2 make a strategy better?”
            ↓
    YouTube long-form
            ↓
    3–5 Reels / Shorts
            ↓
    IG carousel
            ↓
    infographic
            ↓
    website/research note
            ↓
    product insight / feature
            ↓
    user questions
            ↓
    next research question

Tujuannya bukan spam cross-posting, tetapi mengubah satu pekerjaan riset serius menjadi beberapa format.

---

# Content → Product Flywheel

    Audience Question
          ↓
    Research Question
          ↓
    Backtest Lab Experiment
          ↓
    Evidence
       ↙       ↘
    Content   Product Improvement
       ↓            ↓
    Audience      Users
       └──────┬─────┘
              ↓
        New Questions

Content marketing menjadi bagian dari R&D, bukan departemen terpisah yang harus terus mencari topik.

---

# Content Evidence Rules

Setiap konten research sebaiknya menjelaskan:
- hypothesis/question;
- dataset/period;
- sample size;
- protocol;
- assumptions;
- result;
- uncertainty/limitations;
- apakah exploratory atau confirmatory bila relevan.

Jangan:
- cherry-pick equity curve tanpa konteks;
- menyebut hasil historical sebagai jaminan future;
- mengubah parameter diam-diam setelah melihat hasil;
- menggunakan AI-generated number sebagai evidence;
- menjadikan satu eksperimen kecil sebagai universal rule.

---

# CTA Philosophy

CTA harus sesuai konteks.

Examples:
- “Tes klaimnya sendiri.”
- “Lihat protocol eksperimennya.”
- “Coba ubah asumsi dan lihat apakah hasilnya bertahan.”
- “Experiment Passport ada di deskripsi/report.”

Hindari menjadikan setiap video iklan agresif.

---

# Idea Inbox

Tambahkan ide mentah di sini sebelum dikategorikan.

| Idea | Platform | Pillar | Status | Notes |
|---|---|---|---|---|
| RR tidak menentukan actual WR | YouTube + Reels + IG | Trading Math | Idea | benchmark visual |
| 100 parameter tests & false positives | YouTube + Carousel | Research Integrity | Idea | FDR/Bonferroni |
| Build Backtest Lab from zero | YouTube series | Build in Public | Idea | episodic |
| Why AI is not source of truth | Reels + YouTube | AI / Research | Idea | engine vs assistant |
| Strategy Destruction Lab | YouTube + Reels | Robustness | Idea | product + education |
| Backtest-to-Live Gap | YouTube + Carousel | Trading Reality | Idea | flagship topic |

Status vocabulary suggestion: IDEA → RESEARCHING → SCRIPT → RECORD → EDIT → PUBLISHED → REPURPOSED.

---

# Open Decisions

Still undecided:
- channel/account naming;
- visual identity;
- posting cadence;
- language mix;
- face-cam vs voice-over balance;
- exact launch campaign;
- affiliate policy/disclosure;
- whether long-form content publishes full datasets/reports publicly.

Do not force these decisions until the product/content identity is more mature.
