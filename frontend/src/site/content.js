// Public-site copy (Indonesian default, English for the marketing pages). Rules for every sentence here:
//  * it must be true of the product in this repository today, or it is written as a limitation;
//  * every differentiator is a CLAIM with evidence files that must exist (tests/site-content.test.mjs checks the paths);
//  * no promise of profit, no live trading, no investment advice, no unlicensed-data claim.
// Legal pages are DRAFTS for the owner and a legal adviser; they stay blocked from release until SITE.legalApproval is filled.

export const LANGS = ['id', 'en'];

// Differentiators: key, evidence (repo-relative paths that prove it), copy per language (id, en).
export const CLAIMS = [
  {key: 'tick-bid-ask', evidence: ['backend/execution/engine.py', 'backend/tests/test_tick_execution.py'],
    id: {t: 'Mesin tick bid/ask, bukan tebakan dari candle', d: 'Beli terisi di Ask, jual di Bid, dan stop atau target terpicu oleh tick yang benar-benar tercatat. Hasil tidak pernah ditentukan dari candle; bila data tidak cukup, hasilnya ditulis tidak pasti, bukan dikarang.'},
    en: {t: 'A bid/ask tick engine, not candle guesses', d: 'Buys fill at Ask, sells at Bid, and stops or targets trigger on recorded ticks. A result is never decided from a candle; when evidence is missing, the outcome is shown as unresolved, not invented.'}},
  {key: 'no-look-ahead', evidence: ['backend/ticks/timeline.py', 'backend/tests/test_tick_timeline.py'],
    id: {t: 'Tanpa mengintip masa depan', d: 'Grafik hanya menampilkan pasar yang sudah diputar. Tick yang belum terungkap tidak pernah sampai ke layar maupun ke perhitungan, dan tick dengan waktu yang sama diproses utuh.'},
    en: {t: 'No peeking at the future', d: 'The chart shows only the market that has been replayed. Ticks that have not been revealed never reach the screen or the calculation, and ticks with the same timestamp are processed together.'}},
  {key: 'receipts', evidence: ['backend/tests/test_tick_execution_postgres.py', 'backend/execution/journal_order_index.py'],
    id: {t: 'Hasil yang bisa diaudit', d: 'Setiap perintah menghasilkan bukti tersimpan yang tidak bisa diubah. Jurnal dan statistik dihitung dari peristiwa yang tercatat, sehingga angka yang Anda lihat bisa ditelusuri.'},
    en: {t: 'Results you can audit', d: 'Every command produces a stored, immutable receipt. The journal and statistics are computed from recorded events, so every number can be traced.'}},
  {key: 'jump', evidence: ['backend/execution/jump_next_event.py', 'backend/tests/test_window_jump.py'],
    id: {t: 'Lompat ke kejadian berikutnya', d: 'Tidak perlu memutar setiap tick. Jump membawa replay langsung ke peristiwa berikutnya pada order Anda, dengan aturan yang sama seperti replay biasa.'},
    en: {t: 'Jump to the next event', d: 'No need to replay every tick. Jump moves the replay straight to the next event on your orders, under the same rules as a normal replay.'}},
  {key: 'orders', evidence: ['backend/tests/test_tick_execution.py', 'backend/execution/engine.py'],
    id: {t: 'Order yang dipakai trader sungguhan', d: 'Order pasar dan terencana dengan stop dan target, ukuran berdasarkan persen risiko, beberapa posisi aktif sekaligus, serta pembatalan dan penutupan manual.'},
    en: {t: 'Orders traders actually use', d: 'Market and planned orders with stop and target, risk-percent sizing, several open positions at once, and manual cancel and close.'}},
  {key: 'journal-analytics', evidence: ['backend/execution/analytics_projection.py', 'backend/cloud/export_results.py', 'backend/cloud/export_pdf.py'],
    id: {t: 'Jurnal, analitik, dan ekspor', d: 'Win rate, profit factor, drawdown, rata-rata R, dan kurva saldo per Sesi, ditambah ekspor CSV dan laporan PDF dari catatan yang sama.'},
    en: {t: 'Journal, analytics and export', d: 'Win rate, profit factor, drawdown, average R and a balance curve per Session, plus CSV export and a PDF report built from the same records.'}},
  {key: 'recovery', evidence: ['backend/tests/test_research_queue.py', 'backend/tests/test_replay_run.py'],
    id: {t: 'Sesi yang selamat dari gangguan', d: 'Setiap Sesi menyimpan posisi replay, order, dan saldo. Bila proses terhenti di tengah jalan, Sesi dilanjutkan tanpa order ganda dan tanpa saldo berubah.'},
    en: {t: 'Sessions that survive interruptions', d: 'Every Session keeps its replay position, orders and balance. If a process stops midway, the Session resumes with no duplicate order and no balance change.'}},
  {key: 'isolation', evidence: ['backend/tests/test_cloud_research.py', 'backend/cloud/entitlements.py'],
    id: {t: 'Data tiap pengguna terpisah', d: 'Setiap akun hanya melihat Sesi miliknya. Batas paket Free dan Pro ditegakkan di server, bukan di browser.'},
    en: {t: 'Each user’s data is separate', d: 'Every account sees only its own Sessions. Free and Pro limits are enforced on the server, not in the browser.'}},
];

const REQUIRED = '[diisi oleh pemilik]';
export const fill = (text, site) => text
  .replaceAll('{{brand}}', site.brand)
  .replaceAll('{{legalName}}', site.business.legalName || REQUIRED)
  .replaceAll('{{email}}', site.business.email || REQUIRED)
  .replaceAll('{{address}}', site.business.address || REQUIRED)
  .replaceAll('{{domain}}', site.domain || REQUIRED)
  .replaceAll('{{refundDays}}', site.refund.windowDays == null ? REQUIRED : String(site.refund.windowDays))
  .replaceAll('{{refundConditions}}', site.refund.conditions || REQUIRED);

export const COPY = {
  id: {
    lang: 'id', other: 'en', otherLabel: 'English',
    nav: {how: 'Cara kerja', why: 'Keunggulan', plans: 'Paket', faq: 'FAQ', pricing: 'Harga', about: 'Tentang', contact: 'Kontak', terms: 'Syarat & Ketentuan', privacy: 'Kebijakan Privasi', refund: 'Pengembalian Dana', open: 'Masuk / Daftar', home: 'Beranda'},
    hero: {
      badge: 'Simulator backtest berbasis tick', title: 'Latihan trading di pasar kemarin, dengan hasil yang bisa dipercaya.',
      lead: 'RIKSORA Backtest Lab memutar ulang data tick bid/ask historis. Anda menulis aturan, menjalankan Sesi, lalu server menghitung hasilnya dari bukti tick, bukan dari tebakan pada candle.',
      primary: 'Mulai gratis', secondary: 'Lihat harga',
      caption: 'Simulasi untuk berlatih. Tanpa uang sungguhan, tanpa eksekusi di broker, bukan nasihat investasi.'},
    purpose: {
      title: 'Untuk apa produk ini dibuat',
      body: [
        'Banyak backtest berbasis candle menebak di mana order terisi dan tanpa sengaja memakai informasi dari masa depan. Hasilnya terlihat bagus di layar tetapi sulit dipercaya.',
        'RIKSORA dibuat untuk satu tujuan: memberi trader tempat berlatih dan menguji aturan dengan cara yang jujur. Pasar diputar ulang tick demi tick, order terisi di harga bid atau ask yang tercatat, dan setiap hasil bisa ditelusuri.',
        'Cocok untuk trader ritel yang ingin menguji aturan dan melatih disiplin, pelajar yang ingin memahami bagaimana order bekerja, dan peneliti strategi yang membutuhkan hasil yang bisa diulang.']},
    whyTitle: 'Apa yang membuatnya berbeda',
    how: {title: 'Tiga langkah, satu kebiasaan', steps: [
      ['Tulis aturan, mulai Sesi', 'Tulis aturan Anda sekali, lalu pilih instrumen, bulan awal, dan saldo. Grafik berhenti tepat di titik itu.'],
      ['Putar dan trading', 'Tekan Play, Step, atau Jump. Pasang order pasar atau rencana dengan stop dan target saat setup Anda muncul.'],
      ['Belajar dari hasilnya', 'Setiap trade masuk ke jurnal dan analitik: win rate, profit factor, drawdown, dan kurva saldo.']]},
    plans: {title: 'Paket Free dan Pro', lead: 'Mulai gratis. Pro membuka kuota tanpa batas bila Anda ingin berlatih lebih banyak.', cta: 'Lihat harga dan aturan lengkap'},
    limits: {title: 'Yang perlu Anda ketahui', items: [
      'Ini simulasi untuk berlatih dan riset. Tidak ada uang sungguhan, tidak ada eksekusi di broker, dan bukan nasihat investasi.',
      'Kinerja masa lalu tidak menjamin hasil di masa depan. Hasil simulasi dapat berbeda dari trading nyata (spread, slippage, likuiditas, dan faktor psikologis).',
      'Produk dalam tahap awal (beta). Saat ini fokus pada XAUUSD; instrumen lain menyusul setelah profil dan datanya disetujui.',
      'Periode dan instrumen yang tersedia ditampilkan di dalam aplikasi sesuai katalog data dan persetujuan sumber data.',
      'Batas Free dan Pro dihitung berdasarkan hari dan bulan UTC.']},
    faq: {title: 'Pertanyaan umum', items: [
      ['Apakah ini broker atau menggunakan uang sungguhan?', 'Bukan. RIKSORA adalah simulator. Saldo di dalamnya adalah saldo latihan dan tidak ada order yang dikirim ke pasar.'],
      ['Data apa yang dipakai?', 'Data historis tick bid/ask. Instrumen dan periode yang tersedia ditampilkan di aplikasi sesuai katalog. Saat ini fokus pada XAUUSD.'],
      ['Apakah hasil simulasi menjamin profit?', 'Tidak. Hasil simulasi hanya alat belajar dan riset, bukan janji hasil trading.'],
      ['Bagaimana cara membayar Pro?', 'Pembayaran diproses oleh Midtrans. Metode pembayaran yang tersedia tercantum di halaman Harga. RIKSORA tidak menyimpan data kartu Anda.'],
      ['Apakah Pro diperpanjang otomatis?', 'Tidak. Pro dibeli per periode dan berakhir saat masa berlakunya habis. Anda memperpanjang secara manual bila ingin.'],
      ['Bagaimana bila saya ingin pengembalian dana?', 'Lihat halaman Pengembalian Dana untuk syarat dan caranya.']]},
    footer: {disclaimer: 'Simulasi untuk berlatih. Bukan nasihat investasi. Kinerja masa lalu tidak menjamin hasil di masa depan.', rights: 'Hak cipta dilindungi.'},
    pricing: {
      title: 'Harga dan paket', lead: 'Harga dalam Rupiah (IDR). Mulai gratis, tingkatkan ke Pro bila perlu.',
      free: {name: 'Free', price: 'Rp 0', per: 'selamanya', features: [
        '1 Sesi baru per bulan kalender (UTC)', '1 bulan historis baru diaktifkan per hari (UTC)', 'Melanjutkan Sesi yang ada tidak mengurangi kuota',
        'Memakai ulang bulan yang sudah diaktifkan tidak mengurangi kuota', 'Replay tick, order, Jump, jurnal, analitik, dan ekspor CSV/PDF']},
      pro: {name: 'Pro', monthlyName: 'Pro Bulanan', yearlyName: 'Pro Tahunan', perMonth: 'per bulan (30 hari)', perYear: 'per tahun (365 hari)', was: 'harga normal', saving: 'hemat', until: 'sampai', per: 'per periode', features: [
        'Sesi baru tanpa batas kuota', 'Bulan historis baru tanpa batas kuota', 'Semua fitur Free',
        'Aktif sampai masa berlaku habis, tidak diperpanjang otomatis']},
      pending: 'Harga akan diumumkan', buy: 'Masuk untuk membeli Pro',
      rulesTitle: 'Aturan kuota dengan jelas', rules: [
        'Free: satu Sesi baru per bulan kalender UTC dan satu bulan historis baru per hari UTC.',
        'Melanjutkan Sesi yang sudah ada dan memakai ulang bulan yang sudah diaktifkan tidak memakai kuota.',
        'Kuota diatur ulang pada pukul 00.00 UTC, yaitu pukul 07.00 WIB.',
        'Status Pro hanya berasal dari pembayaran yang sudah lunas dan belum kedaluwarsa, dan ditegakkan oleh server.',
        'Pro tidak diperpanjang otomatis.'],
      payTitle: 'Pembayaran', payLead: 'Pembayaran diproses oleh Midtrans. RIKSORA tidak menyimpan data kartu atau rekening Anda.', payMethods: 'Metode pembayaran', taxNone: 'Informasi pajak akan dicantumkan sebelum pembelian.'},
    about: {title: 'Tentang RIKSORA', body: [
      'RIKSORA Backtest Lab adalah simulator backtest berbasis tick untuk trader yang ingin berlatih dan menguji aturan dengan jujur.',
      'Kami percaya hasil latihan hanya berguna bila prosesnya jujur: tanpa mengintip masa depan, tanpa menebak isian order, dan dengan bukti yang bisa ditelusuri.',
      'Produk ini masih dalam tahap awal. Kami menuliskan batasannya secara terbuka di halaman beranda dan di dalam aplikasi.'],
      principlesTitle: 'Prinsip kami', principles: ['Hasil dihitung dari bukti tick, bukan dari candle.', 'Tidak ada informasi masa depan di layar maupun di perhitungan.', 'Setiap hasil bisa ditelusuri ke catatan yang tidak berubah.', 'Batasan produk ditulis terbuka.'],
      identityTitle: 'Identitas usaha'},
    contact: {title: 'Kontak', lead: 'Pertanyaan tentang akun, pembayaran, atau pengembalian dana? Hubungi kami.', email: 'Email', phone: 'Telepon / WhatsApp', address: 'Alamat', hours: 'Jam layanan', response: 'Waktu respons', data: 'Permintaan data pribadi (akses, koreksi, penghapusan) dapat dikirim ke email di atas.'},
    legalDraft: 'DRAF untuk ditinjau pemilik dan penasihat hukum. Belum disetujui untuk dipublikasikan.',
    updated: 'Terakhir diperbarui',
    terms: {title: 'Syarat dan Ketentuan', sections: [
      ['1. Layanan', ['{{brand}} ({{domain}}) adalah layanan simulasi backtest berbasis data tick historis, dikelola oleh {{legalName}}. Layanan ini untuk berlatih dan riset.']],
      ['2. Bukan nasihat investasi', ['Layanan ini tidak menyediakan nasihat investasi, rekomendasi transaksi, atau eksekusi order di pasar sungguhan. Semua saldo dan order adalah simulasi.', 'Kinerja masa lalu tidak menjamin hasil di masa depan. Hasil simulasi dapat berbeda dari trading nyata.']],
      ['3. Akun', ['Anda bertanggung jawab atas kerahasiaan akun dan atas aktivitas di dalamnya. Anda harus memberikan informasi yang benar dan berusia di atas 18 tahun atau cakap hukum menurut hukum yang berlaku.']],
      ['4. Paket Free dan Pro', ['Free dibatasi satu Sesi baru per bulan kalender UTC dan satu bulan historis baru per hari UTC. Pro tidak dibatasi kuota tersebut.', 'Pro dibeli per periode, tidak diperpanjang otomatis, dan aktif sampai masa berlakunya habis. Harga dan periode tercantum di halaman Harga.']],
      ['5. Pembayaran', ['Pembayaran diproses oleh Midtrans dalam Rupiah. Kami tidak menyimpan data kartu atau rekening Anda.', 'Pro aktif setelah pembayaran terkonfirmasi lunas oleh penyedia pembayaran.']],
      ['6. Penggunaan yang dilarang', ['Dilarang mengganggu layanan, mengakses data pengguna lain, mengambil data secara massal, atau memakai layanan untuk tujuan melanggar hukum.']],
      ['7. Data dan hak kekayaan intelektual', ['Perangkat lunak dan antarmuka adalah milik {{legalName}}. Data pasar historis tunduk pada ketentuan sumbernya dan tidak boleh disalin atau didistribusikan ulang. Catatan Sesi Anda adalah milik Anda.']],
      ['8. Ketersediaan dan perubahan', ['Layanan masih dalam tahap awal. Kami dapat mengubah fitur, kuota, atau harga dengan pemberitahuan yang wajar; perubahan harga tidak berlaku surut pada periode Pro yang sudah dibayar.']],
      ['9. Batas tanggung jawab', ['Sejauh diizinkan hukum, kami tidak bertanggung jawab atas kerugian yang timbul dari keputusan trading yang Anda ambil berdasarkan hasil simulasi.']],
      ['10. Penghentian', ['Anda dapat berhenti memakai layanan kapan saja. Kami dapat menangguhkan akun yang melanggar ketentuan ini.']],
      ['11. Hukum yang berlaku dan kontak', ['Ketentuan ini tunduk pada hukum Republik Indonesia. Pertanyaan dapat dikirim ke {{email}}.']]]},
    privacy: {title: 'Kebijakan Privasi', sections: [
      ['1. Pengelola data', ['{{legalName}} ({{address}}) mengelola data pribadi Anda untuk menjalankan {{brand}}. Kontak: {{email}}.']],
      ['2. Data yang kami kumpulkan', ['Email dan kata sandi (disimpan dalam bentuk hash), pengenal akun Google bila Anda masuk dengan Google, Sesi, order, dan catatan simulasi yang Anda buat, status paket dan riwayat pesanan, serta catatan keamanan dasar (misalnya waktu dan alamat IP untuk membatasi penyalahgunaan).', 'Kami tidak menyimpan data kartu atau rekening; itu ditangani Midtrans.']],
      ['3. Tujuan penggunaan', ['Menyediakan layanan simulasi, mengelola akun dan paket, memproses pembayaran, menjaga keamanan, dan menanggapi permintaan dukungan.']],
      ['4. Pihak ketiga', ['Midtrans (pemrosesan pembayaran), Google (masuk dengan Google, opsional), serta penyedia infrastruktur hosting dan email yang kami gunakan. Kami tidak menjual data pribadi Anda.']],
      ['5. Penyimpanan', ['Data akun disimpan selama akun aktif. Catatan keuangan simulasi bersifat bukti yang tidak dapat diubah dan dihapus sesuai kebijakan retensi yang berlaku. Anda dapat meminta penghapusan akun lewat email di atas.']],
      ['6. Hak Anda', ['Sesuai peraturan pelindungan data pribadi yang berlaku, Anda dapat meminta akses, koreksi, atau penghapusan data pribadi Anda melalui {{email}}.']],
      ['7. Keamanan', ['Kami memakai koneksi terenkripsi, pembatasan akses, dan pemisahan data antar pengguna. Tidak ada sistem yang dapat menjamin keamanan mutlak; kami akan memberi tahu bila terjadi insiden yang memengaruhi data Anda sesuai ketentuan.']],
      ['8. Perubahan kebijakan', ['Perubahan penting akan diumumkan di situs ini dengan tanggal pembaruan.']]]},
    refund: {title: 'Kebijakan Pengembalian dan Pembatalan', sections: [
      ['1. Free', ['Paket Free tidak berbayar sehingga tidak ada pengembalian dana.']],
      ['2. Pro', ['Pro adalah layanan digital yang dibeli per periode dan tidak diperpanjang otomatis, jadi tidak ada penagihan berulang yang perlu dibatalkan.']],
      ['3. Pengembalian dana', ['Permintaan pengembalian dana dapat diajukan dalam {{refundDays}} hari sejak pembayaran. Syarat: {{refundConditions}}.', 'Ajukan lewat {{email}} dengan menyebut email akun dan nomor pesanan. Dana dikembalikan ke metode pembayaran asal sesuai proses penyedia pembayaran.']],
      ['4. Pembayaran ganda atau gagal', ['Bila Anda terbayar dua kali atau pembayaran berhasil tetapi Pro belum aktif, hubungi kami dengan nomor pesanan; kami akan memeriksa dan memperbaikinya.']]]},
  },
  en: {
    lang: 'en', other: 'id', otherLabel: 'Bahasa Indonesia',
    nav: {how: 'How it works', why: 'Why RIKSORA', plans: 'Plans', faq: 'FAQ', pricing: 'Pricing', about: 'About', contact: 'Contact', terms: 'Terms', privacy: 'Privacy', refund: 'Refunds', open: 'Sign in / Register', home: 'Home'},
    hero: {
      badge: 'Tick-based backtest simulator', title: 'Practice trading on yesterday’s market, with results you can trust.',
      lead: 'RIKSORA Backtest Lab replays historical bid/ask tick data. You write your rules, run a Session, and the server computes the result from tick evidence, not from guesses on candles.',
      primary: 'Start free', secondary: 'See pricing',
      caption: 'Simulation for practice. No real money, no broker execution, not investment advice.'},
    purpose: {
      title: 'Why this product exists',
      body: [
        'Many candle-based backtests guess where an order filled and quietly use information from the future. The result looks good on screen but is hard to trust.',
        'RIKSORA has one purpose: give traders an honest place to practice and test rules. The market is replayed tick by tick, orders fill at the recorded bid or ask, and every result can be traced.',
        'It suits retail traders who want to test rules and build discipline, learners who want to see how orders really work, and strategy researchers who need repeatable results.']},
    whyTitle: 'What makes it different',
    how: {title: 'Three steps, one habit', steps: [
      ['Write rules, start a Session', 'Write your rules once, then pick the instrument, start month and balance. The chart stops right there.'],
      ['Replay and trade', 'Press Play, Step or Jump. Place a market or planned order with stop and target when your setup appears.'],
      ['Learn from the results', 'Every trade lands in the journal and analytics: win rate, profit factor, drawdown and the balance curve.']]},
    plans: {title: 'Free and Pro plans', lead: 'Start free. Pro removes the quotas when you want to practice more.', cta: 'See pricing and full rules'},
    limits: {title: 'What you should know', items: [
      'This is simulation for practice and research. No real money, no broker execution, and not investment advice.',
      'Past performance does not guarantee future results. Simulated results can differ from real trading (spread, slippage, liquidity and psychology).',
      'The product is in an early (beta) stage. It currently focuses on XAUUSD; other instruments follow once their profiles and data are approved.',
      'Available periods and instruments are shown inside the app according to the data catalog and data-source approval.',
      'Free and Pro limits are counted by UTC day and month.']},
    faq: {title: 'Frequently asked questions', items: [
      ['Is this a broker, or does it use real money?', 'No. RIKSORA is a simulator. The balance is a practice balance and no order is sent to any market.'],
      ['What data does it use?', 'Historical bid/ask tick data. Available instruments and periods are shown in the app according to the catalog. It currently focuses on XAUUSD.'],
      ['Do simulated results guarantee profit?', 'No. Simulated results are a learning and research tool, not a promise of trading returns.'],
      ['How do I pay for Pro?', 'Payments are processed by Midtrans. Available payment methods are listed on the Pricing page. RIKSORA does not store your card details.'],
      ['Does Pro renew automatically?', 'No. Pro is bought per period and ends when it expires. You renew manually if you want to.'],
      ['What if I want a refund?', 'See the Refunds page for the conditions and how to ask.']]},
    footer: {disclaimer: 'Simulation for practice. Not investment advice. Past performance does not guarantee future results.', rights: 'All rights reserved.'},
    pricing: {
      title: 'Pricing and plans', lead: 'Prices are in Indonesian Rupiah (IDR). Start free, upgrade to Pro when you need to.',
      free: {name: 'Free', price: 'Rp 0', per: 'forever', features: [
        '1 new Session per calendar month (UTC)', '1 newly activated historical month per day (UTC)', 'Continuing an existing Session uses no quota',
        'Re-using an already activated month uses no quota', 'Tick replay, orders, Jump, journal, analytics and CSV/PDF export']},
      pro: {name: 'Pro', monthlyName: 'Pro Monthly', yearlyName: 'Pro Yearly', perMonth: 'per month (30 days)', perYear: 'per year (365 days)', was: 'regular price', saving: 'save', until: 'until', per: 'per period', features: [
        'New Sessions with no quota', 'Newly activated historical months with no quota', 'Everything in Free',
        'Active until the period ends, no automatic renewal']},
      pending: 'Price to be announced', buy: 'Sign in to buy Pro',
      rulesTitle: 'The quota rules, plainly', rules: [
        'Free: one new Session per UTC calendar month and one newly activated historical month per UTC day.',
        'Continuing an existing Session and re-using an already activated month uses no quota.',
        'Quotas reset at 00:00 UTC, which is 07:00 WIB.',
        'Pro status comes only from a paid, unexpired payment and is enforced by the server.',
        'Pro does not renew automatically.'],
      payTitle: 'Payment', payLead: 'Payments are processed by Midtrans. RIKSORA does not store your card or account details.', payMethods: 'Payment methods', taxNone: 'Tax information will be shown before purchase.'},
    about: {title: 'About RIKSORA', body: [
      'RIKSORA Backtest Lab is a tick-based backtest simulator for traders who want to practice and test rules honestly.',
      'We believe practice is only useful when the process is honest: no peeking at the future, no guessing order fills, and evidence you can trace.',
      'The product is early. We state its limits openly on the home page and inside the app.'],
      principlesTitle: 'Our principles', principles: ['Results come from tick evidence, not candles.', 'No future information on screen or in the calculation.', 'Every result traces back to an immutable record.', 'Product limits are written openly.'],
      identityTitle: 'Business identity'},
    contact: {title: 'Contact', lead: 'Questions about your account, payment or a refund? Get in touch.', email: 'Email', phone: 'Phone / WhatsApp', address: 'Address', hours: 'Support hours', response: 'Response time', data: 'Requests about personal data (access, correction, deletion) can be sent to the email above.'},
    legalDraft: 'The legal pages are published in Bahasa Indonesia. An English summary is available on request.',
    updated: 'Last updated',
  },
};
// The legal pages (terms, privacy, refund) exist in Indonesian only; the English site links to the Indonesian text.
COPY.en.terms = COPY.id.terms; COPY.en.privacy = COPY.id.privacy; COPY.en.refund = COPY.id.refund;
