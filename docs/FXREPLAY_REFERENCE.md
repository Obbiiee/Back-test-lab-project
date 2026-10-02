# FXReplay UI/UX reference

Catatan eksplorasi FXReplay sebagai acuan Backtest Lab. Dibuat dari sesi Free akun yang sedang terbuka pada 1 Oktober 2026. Ini adalah catatan perilaku dan hierarki produk, bukan spesifikasi untuk menyalin merek/aset visual secara persis.

## Navigasi utama

- **Testing**: dashboard performa, daftar sesi, daftar trade, dan analitik.
- **Live**: area trading live.
- **Strategies**: alur merumuskan strategi dan mengelola strategi.
- **Battles**: tantangan kompetitif.
- **Education**: pembelajaran.
- **Settings**: akun, paket, perangkat, pengaturan backtest, biaya, jurnal, sesi terhapus, template, dan patent markings.

## Alur Testing yang terlihat

1. Dashboard menampilkan pintasan **Start a session**, simulasi prop firm, tutorial, ringkasan metrik, grafik waktu yang diinvestasikan, dan sesi terbaru.
2. Kartu sesi merangkum nama, simbol, rentang tanggal, saldo, sisa hari, progres, dan tautan Summary.
3. Halaman **Sessions** memilih satu sesi; menyediakan nama/deskripsi, saldo, ringkasan P&L, win rate, risk/reward, gain/loss harian/mingguan/bulanan, daftar trade, jurnal, dan tombol menuju chart.
4. Halaman **Trades** punya filter bertingkat untuk catatan, aset, arah, hasil, tipe, rentang tanggal, tahun, bulan, hari, dan jam. Filter dapat dibersihkan atau diterapkan.
5. Halaman **Analytics** memisahkan Sessions dan Prop firm. Filter meliputi tipe, aset, arah, hasil, tag, sesi, strategi, hari, jam, zona waktu, dan tanggal backtest; hasil dapat diunduh atau dibagikan ketika data tersedia.
6. Halaman **Strategies** memulai dengan pertanyaan apakah pengguna sudah punya strategi. Pilihan yang ditampilkan: memperjelas aturan strategi yang ada, atau mulai dari awal.

## Workspace chart sesi

Chart sesi yang sudah tersimpan dapat dibuka meski kuota sesi baru habis. Workspace ini memakai chart sebagai kanvas utama dengan:

- Header berisi simbol/timeframe, jenis chart, indikator, analytics, undo/redo, penyimpanan layout, tema, keyboard shortcuts, snapshot, dan code editor.
- Toolbar gambar vertikal berkelompok: kursor, garis/trendline, Fibonacci, pola, proyeksi posisi, bentuk, teks/catatan, emoji, serta ukur. Ada magnet, lock, sembunyikan/hapus gambar, dan mode keep drawing.
- Kontrol replay di bawah chart: kecepatan, candle sebelumnya, play/pause, timeframe, candle berikutnya, lompat tanggal, dan undock.
- Tiket Buy/Sell dan kuantitas di panel bawah; saldo akun tampak terpisah. Panel pendamping dapat menampilkan positions/orders, object tree, watchlist, journal, dan news.
- Area bawah chart memiliki rentang cepat 1D/5D/1M/3M/6M/1Y/All, tanggal, zona waktu, skala persen/log/otomatis.

Sesi referensi **Backtest Lab Reference - New Chart** (`9588c6a8-e252-42f0-a287-ccf5f7d18a7a`) menampilkan XAUUSD 1h, saldo awal $100.000, tombol replay, tiket order, dan volume. Saat sesi dilanjutkan, jurnal sudah memiliki satu trade long sebelumnya: entry Stop pada 3 Jun 2024 13:00, size 105, stop loss 2.320,311, take profit 2.358,076, exit 4 Jun 2024 19:59 pada 2.327,128, dan P/L bersih -$767,55. Jurnal menampilkan detail trade, tanggal modifikasi, tab Tag groups/Details, dan catatan yang dapat diedit.

Pada backtest berikutnya, tiga trade tambahan dieksekusi dengan target RR 1:1 dan risiko sekitar 0,5% saldo per trade: long 0,21 lot dari 2.337,895 (SL 2.314,516; TP 2.361,274) mencapai TP pada 6 Jun 2024 01:14 (+$490,96); long 0,21 lot dari 2.369,288 (SL 2.345,595; TP 2.392,981) mencapai SL pada 7 Jun 2024 08:40 (-$497,55); short 0,19 lot dari 2.336,485 (SL 2.361,533; TP 2.311,437) mencapai TP pada 7 Jun 2024 13:50 (+$475,91). Ketiganya sudah tertutup. Total sesi termasuk trade lama: 2 menang, 2 kalah, P/L bersih -$298,23, saldo $99.701,77. Backtest dihentikan di titik ini sesuai arahan pengguna.

Alur tombol Long/Short Position pada toolbar kiri lebih berperan sebagai alat proyeksi risiko/imbalan di chart. Alat itu tidak otomatis mengirim order: tiket order tetap perlu dipilih/diisi terpisah, termasuk sisi Buy/Sell dan level SL/TP. Ini perilaku penting untuk ditiru dengan pemisahan yang jelas antara gambar rencana posisi dan order yang benar-benar tercatat.

## Analitik dan simulasi sesi

- **Performance** merangkum equity/P&L sepanjang waktu, total P&L dan saldo, persentase gain, win rate, jumlah trade, average/ideal RR, expectancy, profit factor, pemenang dan pecundang, performa per sisi/sesi/waktu/hari/bulan, kalender performa, serta frekuensi trade.
- Snapshot awal saat hanya trade lama yang ada: total P&L -$767,55 (-0,77%), saldo $99.232,45, win rate 0%, dan 0/1 kemenangan. Durasi trade tercatat 1 hari 6 jam 59 menit.
- Snapshot akhir setelah 4 trade tertutup: total P&L -$298,23 (-0,30%), saldo $99.701,77, win rate 50% (2/4), 0 trade impas, average RR 1 dan max RR 1. Ideal average RR 2,06; max ideal RR 2,13; could-have-profit/breakeven RR 1 (max ideal 1,42); expectancy -$74,56; profit factor 0,76. Rincian Winners/Losers menampilkan dua pemenang (best/average win +0,49%, durasi rata-rata 11 jam 3 menit) dan dua pecundang (worst -0,77%, average loss -0,63%, durasi rata-rata 1 hari 5 jam 20 menit). Performance by side menunjukkan 75% trade BUY dan 25% SELL. Kalender aktivitas menunjukkan trade pada 3, 5, 6, dan 7 Jun 2024.
- **Drawdown** menampilkan drawdown ekuitas maksimum, rata-rata, waktu pemulihan, frekuensi drawdown, dan Maximum Adverse Excursion. Nilai yang terlihat: max drawdown -0,8%, rata-rata -0,77%, pemulihan 0 hari, frekuensi 1.
- **Simulation** memuat Stop Loss Simulator, RR Simulator, dan Monte Carlo. Simulator SL memerlukan setidaknya tiga trade yang memiliki SL awal. RR Simulator memerlukan setidaknya tiga trade dan trade pemenang dengan average RR minimal 0,01. Monte Carlo serta beberapa rincian analytics menampilkan pengunci Upgrade pada akun Free.
- Analytics memiliki tab Sessions dan Prop firm; filter global meliputi Type, Assets, Side, Outcome, Tags, Session, Strategy, Day, Time, Timezone, dan Backtesting Date. Tombol Apply hanya aktif setelah filter berubah; tersedia Clear filters, Download CSV, dan Share.
- Grafik equity dapat diubah rentangnya (All, Day, 1 Hour, 15 Min). Grafik menyediakan unduhan SVG/PNG/CSV lewat menu grafik. Bagian lain yang terlihat: expectancy/profit factor, winners/losers, performance by side/session/time/day/month, performance calendar, dan average trade frequency (per hari/minggu/bulan). Beberapa insight waktu/hari/bulan terkunci di paket berbayar.

## Pengaturan yang relevan

- Zona waktu akun dipakai lintas fitur.
- Backtesting: kontrol replay, lompat ke tanggal, log debug, garis Ask, dan penanda perpindahan kontrak futures; beberapa opsi terkunci pada paket Free.
- Spreads & Commissions: konfigurasi per aset yang diterapkan pada sesi baru.
- Pengaturan lain mencakup jurnal, template catatan, dan sesi terhapus.

## Pemetaan ke Backtest Lab

| Pola FXReplay | Kondisi Backtest Lab | Arah UX |
|---|---|---|
| Shell sesi dengan chart sebagai fokus | Top bar, chart candle, toolbar, panel trading, kontrol replay | Pertahankan chart sebagai area utama dan kontrol tetap mudah dijangkau |
| Pengaturan instrumen/sesi sebelum replay | Impor CSV dan pembuatan replay | Lengkapi dengan nama sesi, tanggal mulai/akhir, saldo, biaya, serta ringkasan data |
| Ringkasan posisi dan order | TradingPanel dan PositionTabs | Satukan tabel posisi/order dengan status risiko dan ekuitas |
| Dashboard dan Session detail | Belum menjadi alur produk lengkap | Prioritas berikut: riwayat sesi, halaman ringkasan, jurnal dan analitik |
| Filter Trades dan Analytics | Backtest Lab sudah punya Analytics realized dasar; filter global dan halaman Trades tersaring belum tersedia | Tambahkan filter yang konsisten dan dapat dihapus per chip |
| Strategi sebagai aturan teruji | Belum ada objek strategi | Simpan aturan eksplisit, lalu hubungkan ke simulasi dan laporan |
| Biaya khusus per instrumen | Engine mendukung spread/slippage/komisi pada konfigurasi | Buat preset biaya per simbol dan tunjukkan asumsi pada laporan |
| Toolbar chart dan panel samping | Drawings/indikator ada, tetapi workspace belum selengkap referensi | Tambah kelompok drawing yang dapat dikembangkan, panel watchlist/jurnal, serta kontrol replay yang menetap |

## Batas eksplorasi saat ini

Akun Free menunjukkan pesan bahwa kuota sesi baru telah habis ketika tombol sesi baru ditekan. Tidak ada sesi baru yang dibuat dan tidak ada paket berbayar yang dipilih. FXR Script pada chart dapat menggambar indikator/sinyal, tetapi dokumentasi sandbox menyatakan skrip indikator hanya menghitung candle dan menggambar hasil; ia tidak dapat membuat atau mengelola order. Beberapa simulator/insight punya ambang minimum trade atau terkunci pada akun Free; eksekusi strategi otomatis pada sesi ini belum ditemukan. Backtest berhenti setelah tiga trade tambahan yang sudah tertutup; tidak ada trade terbuka yang tersisa. Halaman yang sudah diamati: Testing Dashboard, Sessions, Trades, Analytics (Performance, Drawdown, Simulation), Strategies, Account Settings, Backtesting Settings, Spreads & Commissions, jurnal, dan chart sesi.

## Rencana tindak lanjut

- Lanjutkan eksplorasi chart dan setup sesi bila akses sesi tersedia kembali.
- Jalankan backtest satu bulan pada data lokal, dengan strategi serta asumsi biaya dinyatakan terang-terangan.
- Gunakan data harga historis yang nyata untuk menilai strategi; dataset contoh XAUUSD lokal saat ini adalah data simulasi.
