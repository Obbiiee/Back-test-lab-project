> HISTORICAL: roadmap prototipe/backend awal. Penomoran dan status di bawah bukan status produk saat ini. Lihat AI_CONTEXT/01_PROJECT_STATE.md dan 04_CURRENT_PHASE.md untuk kondisi aktual serta izin fase.

# Backtest Lab — Roadmap

## Hasil inspeksi kode yang ada (index.html v0.3)

**Sudah berfungsi (prototipe satu file):** chart candle, BUY/SELL, SL/TP, spread, komisi,
slippage, lot dari risiko %, kurva ekuitas, riwayat trade, Play/Next/Previous.

**Utang teknis yang harus diselesaikan:**
- Semua candle (termasuk masa depan) berada di memori browser, jadi belum bebas look-ahead.
- Data acak (80 candle), belum ada impor CSV.
- Logika trading ada di JavaScript frontend, padahal seharusnya di engine backend.
- Tombol PREVIOUS tidak membatalkan trade yang sudah tertutup, hasil bisa tidak konsisten.
- Slippage pada TP dikurangkan dengan cara yang sama seperti pada SL; perlu ditinjau ulang.
- Belum ada tes otomatis.

**Yang bisa dipakai ulang:** rumus lot dari risiko, konsep mode eksekusi SL-first/TP-first,
gaya tampilan (Poppins), susunan panel statistik dan riwayat.

## Fase 1 — Fondasi replay (sedang dikerjakan)
- [x] Model candle ternormalisasi (UTC)
- [x] Impor + validasi CSV (tidak ada perbaikan diam-diam)
- [x] Replay engine + tes anti look-ahead
- [x] Service dan API FastAPI
- [x] Data contoh XAUUSD 1 jam (simulasi)
- [x] Frontend: chart, kontrol replay, dialog impor terhubung ke API
- [x] Uji alur API lokal: impor CSV, mulai replay, dan maju satu candle

## Fase 2 — Order dan eksekusi
Market order, limit/stop, SL/TP dengan kebijakan intrabar yang terdokumentasi, spread,
slippage, komisi, position sizing (engine backend + tes).

**Kemajuan awal:** engine market order backend sudah dibuat dan dites: BUY/SELL, ukuran posisi
dari risiko, spread/slippage/komisi, SL/TP, gap melewati SL, penutupan manual, dan reset.
Jika satu candle menyentuh SL dan TP, SL diproses lebih dulu. Harga OHLC dianggap harga tengah;
jarak SL/TP dihitung dari harga entry aktual. Pengaturan akun default: saldo 10.000, kontrak
100 unit, biaya 0; semua nilai dapat diatur saat memulai replay. Frontend kini memiliki panel
BUY/SELL, risiko dan jarak SL/TP, penutupan manual, riwayat trade, serta marker entry/exit dan
garis harga posisi. Pending order dapat dibatalkan, pemicunya hanya diperiksa saat replay
maju, dan pengisian yang langsung menyentuh SL/TP mengikuti kebijakan SL-first. Analytics kini
menampilkan equity realized dari trade tertutup; floating P&L dan equity akun live masih perlu dibuat.

**Chart:** chart memakai TradingView Lightweight Charts (Apache-2.0). Overlay SMA 20, EMA 20,
dan EMA 50 dapat dinyalakan atau dimatikan langsung pada chart. Indikator dihitung dari candle
yang sudah terlihat di replay agar tidak membaca data masa depan. Tersedia garis harga sekali
klik, trendline dua titik, hapus garis gambar, serta pemilihan harga pending order dari chart
untuk dikonfirmasi di panel trading. Fitur berikutnya: RSI/volume dan pengelolaan order penuh
langsung dari chart.

**Position tool workflow:** Cursor, Long Position, dan Short Position tersedia. Klik chart untuk
membuat proyeksi posisi; Entry, stop, dan target dapat disesuaikan dengan handle. Proyeksi ini
hanya gambar rencana dan tidak mengirim order. Tiket order tetap dikonfirmasi secara terpisah.

**Chart UX — Phase 1 Shell:** top bar, left vertical tool groups, area chart utama, panel kanan,
dan kontrol replay bawah mulai dipisahkan. Dropdown timeframe pada shell hanya demo tampilan;
dataset candle tetap memakai timeframe saat impor. Interaction drawing yang lebih lengkap
menyusul di fase berikutnya.

## Fase 3 — Akun dan P&L
Balance realized dan riwayat trade terhubung ke replay. Berikutnya: floating P&L, equity live
saat posisi masih terbuka, dan batas risiko akun.

## Fase 4 — Jurnal dan analitik
- [x] Analytics posisi tertutup: P&L, saldo, win rate, expectancy, profit factor, average R, winners/losers, performa BUY/SELL, dan hasil harian.
- [x] Kurva equity realized, drawdown maksimum, ekspor CSV trade, dan simulasi target RR berbasis hasil R historis.
- [ ] Jurnal dengan tag/catatan per trade, filter tanggal/aset/arah, dan kalender performa.
- [ ] Statistik sesi dan metrik durasi pemulihan drawdown.

## Fase 5 — Fitur lanjutan
Multi-timeframe (agregasi OHLC), alat gambar, Monte Carlo, simulator prop firm.

## Fase 6 — Produksi
Login, PostgreSQL, penyimpanan cloud, deployment.

## Asumsi yang berlaku sekarang
- Semua waktu disimpan dalam UTC. Timestamp CSV tanpa offset dianggap berada di zona waktu yang dipilih saat impor.
- Gap data (akhir pekan, libur) hanya peringatan; data dengan error ditolak seluruhnya.
- Replay default mulai di candle ke-101 supaya ada riwayat 100 candle di belakang titik mulai.
- Previous hanya menggeser tampilan; kemajuan baru dilacak oleh `high_water`.
