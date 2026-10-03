# Backtest Lab — Corat-Coret & Idea Inbox

> **Status:** Scratchpad / idea inbox  
> **Purpose:** Tempat membuang ide mentah dengan cepat sebelum diputuskan masuk Product Blueprint, Architecture, Roadmap, Research Thesis, atau backlog implementasi.  
> **Rule:** Isi file ini **bukan keputusan final dan bukan implementation authorization**.

## Cara Pakai

Tulis ide dulu. Jangan takut jelek, belum lengkap, atau berubah.

Jika ide sudah matang:
- product/UX → pindahkan atau rangkum ke `PRODUCT_DESIGN_BLUEPRINT.md`
- architecture/data/AI → `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` atau `SCALING_DATA_AI_DECISIONS.md`
- scientific/research → `BACKTEST_LAB_RESEARCH_THESIS.md`
- implementation sequencing → `ROADMAP.md`
- content → kembangkan di `CONTENT_IDEA_LAB.md`

Format opsional:

    [DATE]
    IDEA:
    WHY:
    POSSIBLE FEATURE:
    OPEN QUESTION:
    DESTINATION:

---

## Product Ideas

- Backtest Lab sebagai **Trading Research Laboratory**, bukan sekadar replay platform.
- Basic evidence tetap berguna untuk Free; deeper evidence menjadi Pro.
- Research modules terasa seperti alat laboratorium.
- Locked Pro cards tetap menunjukkan jenis analisis yang tersedia tanpa membocorkan/fabricate hasil.
- Experiment Passport sebagai catatan laboratorium yang membuat hasil reproducible.
- Benchmark selalu hadir dekat metrik utama bila relevan.
- User tetap bebas melakukan eksperimen; software membuat konsekuensi keputusan terlihat dalam data.

## AI Ideas

- AI Research Assistant, bukan trading guru.
- AI menjelaskan verified evidence; deterministic engines tetap source of truth.
- AI dapat menyarankan eksperimen berikutnya untuk mengurangi uncertainty.
- Research Context Builder mengirim konteks relevan saja.
- AI Gateway agar model/provider dapat diganti tanpa membongkar core product.
- Kemungkinan AI membandingkan beberapa Experiment Passport.
- AI bisa membantu membuat research report dari hasil deterministic engines.
- AI tidak memberi label universal “strategi bagus/buruk”.

## Research Ideas

- “Don't trust the claim. Test it.”
- Zero-edge benchmark vs observed results.
- RR break-even benchmark.
- Monte Carlo sebagai distribusi kemungkinan sequence, bukan ramalan market.
- Survival-based risk sizing.
- Strategy Destruction Lab.
- Multiple-testing correction dan pemisahan exploratory vs confirmatory.
- OOS/Walk Forward sebagai fresh evidence.
- Backtest-to-Live Gap.
- Market Regime Engine dengan definisi versioned/deterministic.
- Opportunity accountability: TAKE / EXCLUDE + reason.
- Planned N vs actual N.
- Effective sample size / dependence sebagai research topic lanjutan.

## Business / Monetization Ideas

- Free = Test the idea.
- Pro = Investigate the evidence.
- Jangan menjual freedom; jual **more data + deeper evidence**.
- Lab Protocol tetap accessible agar metodologi yang benar tidak dijadikan paywall.
- Advanced compute seperti Monte Carlo/robustness dapat menjadi natural paid value.
- AI usage dapat dimeter secara terpisah jika biaya inference signifikan.
- Pricing dan quota belum final.

## Infrastructure Ideas

- Feature maturity dan infrastructure capacity adalah dua axis berbeda.
- Profile S → M → L berdasarkan measured workload.
- Data portability harus memungkinkan migrasi server/provider dengan gangguan minimal.
- Shared canonical market datasets; user-specific experiments/results.
- Heavy research jobs asynchronous.
- Core product tetap usable ketika AI provider down.

## UX / Visual Ideas

- Visual language: modern scientific laboratory + professional trading terminal.
- Hindari tampilan “casino”, hype, atau guru-signal.
- Basic Results → Benchmark → Advanced Research.
- Desktop = research workstation.
- Mobile = monitoring/results/journal/AI companion terlebih dahulu.
- Research modules dapat divisualkan sebagai lab cards/workspaces.
- Experiment Passport selalu mudah diakses dari result.

## Random / Wild Ideas

Masukkan ide yang belum layak roadmap di sini.

- Public research reports yang bisa dibagikan dengan anonymized Experiment Passport.
- Strategy “destruction score” jangan berupa skor arbitrer; mungkin tampilkan failure map.
- Compare two protocol versions side-by-side.
- Research lineage: Experiment A → hypothesis → Protocol B → OOS C.
- Dataset health card.
- “What would falsify this strategy thesis?” sebagai prompt AI.
- Community research nanti hanya jika integrity/provenance dapat dijaga.

## Parking Lot

Ide yang menarik tetapi **jangan dikerjakan sekarang**:
- autonomous live real-money execution;
- social/community layer;
- marketplace;
- public strategy leaderboard;
- broker integrations beyond roadmap authorization;
- complex distributed infrastructure before load data exists.

---

## Unsorted Notes

Tambahkan corat-coret baru di bawah garis ini. Tidak perlu rapi.

---

