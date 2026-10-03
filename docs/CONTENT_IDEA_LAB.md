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


# Brand Language & Slogan Bank

> **Status:** Candidate language, not final locked brand copy.  
> Keep these phrases available for website, product UI, research reports, YouTube, Reels, Instagram, campaign concepts and individual Research Labs.

## Primary Brand Candidates

- **Don't Trust the Claim. Test It.**
- **Test the Idea. Understand the Evidence.**
- **From Trading Ideas to Research Evidence.**
- **Measure the Edge. Understand the Uncertainty.**
- **Don't Predict. Test.**
- **Your Strategy Is a Hypothesis. Test It.**
- **Trade Less on Belief. Test More with Evidence.**
- **What Happened Is Only the Beginning.**
- **A Backtest Shows What Happened. Research Asks Why.**
- **Find the Edge. Then Try to Break It.**
- **If It Has an Edge, It Should Survive the Test.**
- **Evidence Before Confidence.**
- **Know What You Know. Measure What You Don't.**
- **The Market Is Uncertain. Your Research Doesn't Have to Be.**
- **You Can't Control the Outcome. You Can Control the Exposure.**
- **Risk Management Doesn't Create Edge. It Gives Edge Time to Show Up.**

## Candidate Brand Hierarchy

Possible structure:

    BACKTEST LAB
    Don't Trust the Claim. Test It.

    Measure the Edge.
    Understand the Uncertainty.

The first line can act as the main brand challenge; the second can explain the research philosophy.

## Research Lab Language

### Strategy Destruction Lab
**Find the Edge. Then Try to Break It.**

### Monte Carlo Lab
**One Backtest. Thousands of Possible Sequences.**

### OOS / Walk Forward
**Fresh Data. Same Hypothesis.**

### Research Integrity
**Evidence Before Confidence.**

### AI Research Assistant
**Ask the Data, Not the Hype.**

## Usage Ideas

**Homepage / hero**
- Don't Trust the Claim. Test It.
- Measure the Edge. Understand the Uncertainty.
- From Trading Ideas to Research Evidence.

**YouTube / documentary hooks**
- Your Strategy Is a Hypothesis. Test It.
- Don't Predict. Test.
- A Backtest Shows What Happened. Research Asks Why.

**Reels / Shorts**
- Evidence Before Confidence.
- Find the Edge. Then Try to Break It.
- What Happened Is Only the Beginning.

**Risk / survival content**
- You Can't Control the Outcome. You Can Control the Exposure.
- Risk Management Doesn't Create Edge. It Gives Edge Time to Show Up.

**Robustness / OOS content**
- If It Has an Edge, It Should Survive the Test.
- Fresh Data. Same Hypothesis.

## Brand Language Principle

Backtest Lab language should challenge **claims**, not attack people.

The brand should communicate:
- curiosity over certainty;
- evidence over hype;
- experiments over opinions;
- uncertainty as something to measure rather than hide;
- research as a process, not a badge of authority.

Avoid language that implies guaranteed profitability, certainty about future market outcomes, or that Backtest Lab can declare a universally “good” strategy.



# Flagship Instagram Campaign — Do You Actually Have an Edge?

> **Status:** Script-ready content concept  
> **Purpose:** Translate the Backtest Lab product thesis into problem-first Instagram content.  
> **Principle:** Do not sell a feature list. Start with a trader problem, expose the evidence question, then introduce the relevant Backtest Lab solution.

## Feed Carousel — 10 Slides

### Slide 1 — Cover
**STRATEGI LO PROFIT. Tapi... beneran punya EDGE?**

Small text: **Profit ≠ proof.**

### Slide 2 — The first doubt
Lo backtest 100 trade. Win rate: **56%**. Equity: **naik**.

Kelihatannya bagus. Tapi pertanyaan sebenarnya:

**56% itu edge atau cuma noise?**

### Slide 3 — Context changes everything
Win rate sendirian **nggak cukup**.

- 56% dari berapa trade?
- RR berapa?
- Spread dihitung?
- Slippage?
- Berapa parameter yang sudah dicoba?

**Context changes everything.**

### Slide 4 — Overfitting
Misalnya lo mencoba **100 variasi strategi** lalu mengambil satu yang paling bagus.

Hasil terbaik itu belum tentu edge. Bisa jadi lo cuma berhasil **menemukan kebetulan terbaik**.

Footer: *Overfitting / data snooping.*

### Slide 5 — Evidence
Backtest seharusnya bukan mencari:

**❌ equity curve paling cantik**

Tetapi mencari:

**seberapa kuat evidence yang kita punya?**

### Slide 6 — Path risk
Kalau edge memang ada, pertanyaan berikutnya:

**SEBERAPA BURUK HASIL YANG MASIH MUNGKIN TERJADI?**

Losing streak. Drawdown. Recovery time. Sequence risk.

### Slide 7 — Risk sizing
Jangan cuma bertanya:

**“Risk 1% aman nggak?”**

Balik pertanyaannya:

**“Berapa risk maksimum kalau gue nggak mau probabilitas DD >30% melebihi 5%?”**

Small text: *Risk sizing from constraints, not folklore.*

### Slide 8 — Backtest vs live
Setelah live rugi, jangan langsung bilang:

**“Strateginya mati.”**

Bandingkan **BACKTEST vs LIVE**:
- risk berubah?
- entry berubah?
- TP ditutup cepat?
- SL digeser?
- setup dilanggar?

### Slide 9 — The process
Trading bukan tentang menghilangkan uncertainty, tetapi membuat keputusan lebih baik di dalam uncertainty.

**TEST → MEASURE → SURVIVE → EXECUTE → AUDIT → IMPROVE**

### Slide 10 — Brand
Kami tidak sedang membangun AI signal, holy grail, atau sekadar chart replay.

**Backtest Lab**

*Turn trading ideas into testable evidence.*

**DON'T TRUST THE CLAIM. TEST IT.**

## Carousel Caption Draft

Gue mulai dari pertanyaan sederhana: kalau sebuah strategi menghasilkan profit ketika di-backtest, bagaimana kita tahu itu benar-benar edge dan bukan kebetulan?

Dari situ masalahnya malah makin besar.

Edge perlu diuji. Uncertainty perlu diukur. Risiko perlu disesuaikan dengan karakter strategi. Hasil perlu di-stress test. Dan ketika masuk live, execution perlu dibandingkan dengan apa yang sebenarnya diuji.

Itu alasan Backtest Lab dibangun.

Bukan untuk menjawab *“trade berikutnya buy atau sell?”*

Tapi untuk membantu menjawab: **“Seberapa kuat evidence di balik keputusan trading gue?”**

🔬 **Don't Trust the Claim. Test It.**

---

## Reels #1 — 56% Win Rate

**Target duration:** ~25–35 seconds.

**Hook (0–3s)**  
“Win rate strategi lo 56%? Gue belum tahu itu bagus atau nggak.”

Visual: **WIN RATE 56%**

**3–10s**  
“Karena 56% dari 50 trade dan 56% dari 2.000 trade itu bukan evidence yang sama.”

Visual: **56% / 50 trades VS 56% / 2,000 trades**

**10–18s**  
“Belum lagi RR, spread, slippage, dan berapa banyak strategi yang lo coba sebelum menemukan angka 56% itu.”

**18–26s**  
“Jadi backtest jangan berhenti di: ‘Win rate gue berapa?’”

Beat.

“Pertanyaan berikutnya adalah: **seberapa kuat evidence-nya?**”

**Close**  
**Backtest Lab — Don't Trust the Claim. Test It.**

---

## Reels #2 — Risk 1%

**Hook**  
**“Siapa yang memutuskan risk 1% itu aman?”**

“Kenapa bukan 0,3%? Kenapa bukan 1,4%?”

“Risk seharusnya nggak berasal dari angka sakral yang diwariskan trader ke trader.”

Visual: **MAX DRAWDOWN > 30%**

“Coba balik pertanyaannya.”

**‘Gue nggak mau probabilitas drawdown di atas 30% lebih dari 5%.’**

Lalu gunakan data strategi dan model risiko untuk mencari ukuran risk yang memenuhi constraint tersebut.

**Risk management nggak menciptakan edge. Ia memberi edge kesempatan untuk bertahan.**

Close: **KNOW YOUR RISK. FIND YOUR RISK. — Backtest Lab 🔬**

---

## Reels #3 — Backtest Profit, Live Boncos

**Hook**  
**“Backtest profit. Live malah boncos. Berarti strateginya mati?”**

Beat.

**“Belum tentu.”**

Visual split:

| BACKTEST | LIVE |
| --- | --- |
| Risk 0.5% | Risk 1.2% |
| RR 1:1.25 | TP closed early |
| Setup A | Entry after loss |
| No intervention | SL moved |

Voice-over:

“Kalau yang lo lakukan ketika live berbeda dari sistem yang lo backtest, lo bahkan belum membuktikan strateginya gagal.”

**“Lo sedang menjalankan eksperimen yang berbeda.”**

Close:

**Test the strategy. Audit the execution.**

**Don't Trust the Claim. Test It.**

## Instagram Editorial Pattern

Default pattern for this campaign and similar posts:

**One trader problem → one uncomfortable question → one evidence concept → one strong visual → Backtest Lab philosophy.**

Avoid leading with feature announcements such as “New Feature: Monte Carlo.” Prefer the user problem first, e.g. **“Risk 1% itu sebenarnya datang dari mana?”** and reveal Monte Carlo/survival modeling as the solution.

The product should be communicated as:

**Test → Measure → Survive → Execute → Audit → Improve**

rather than as a collection of unrelated features.
