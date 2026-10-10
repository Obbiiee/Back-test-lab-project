# Frontend Backtest Lab

Source aktif lokal: `src/main.jsx` → `src/tickAlpha/TickAlphaEntry.jsx`, chart bersama `src/components/CandleChart.jsx`. `/?legacy=local` mempertahankan FigmaWorkspace; lihat [panduan root](../README.md) untuk sumber Exness privat, layanan/database, dan fixture sintetis yang terpisah.
Market/replay, trading/RiskReward, dan drawing memiliki domain terpisah. `src/` adalah source produksi; jangan membuat source tree pengganti.

Jalankan `npm ci`, `npm run dev`. Validasi lengkap dan batas arsitektur dijelaskan di [AI_CONTEXT](../AI_CONTEXT/07_TEST_COMMANDS.md).

`legacy/phase3/` adalah referensi dan fixture geometry historis, bukan runtime aktif. Dua compatibility export (`components/TradingLevels.jsx`, `drawings/position.js`) sengaja dipertahankan.

`tests/browser/` menyimpan harness disposable; gunakan origin pengujian terpisah, jangan menimpa storage preview pengguna. Hasil screenshot/console baru disimpan di `tests/artifacts/` atau `docs/_generated/` yang diabaikan Git. Bukti fase lama yang sudah tercatat tetap dipertahankan.

Generator/reference bundle: `scripts/ai-bundle.mjs`; output `../AI_BUNDLE/` disposable, tidak di-commit. Dependencies, `dist/`, cache dan data download sementara juga diabaikan Git. Data tervalidasi `public/market/` tetap tracked.
