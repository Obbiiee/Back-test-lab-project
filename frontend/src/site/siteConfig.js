// Business facts the OWNER must supply before a public release. Nothing here is invented: every value starts as null and the release gate
// (scripts/verify-site-config.mjs, run by `npm run build:release`) refuses to build while any required value is missing or any legal text is unapproved.
// Prices must equal the server plan (BTL_BILLING_AMOUNT_IDR / BTL_BILLING_DURATION_SECONDS); the same release checklist compares them.
export const SITE = {
  brand: 'RIKSORA Backtest Lab',
  // 'preview': the application is not open to the public yet; the site shows product, prices and policies and replaces sign-in with a beta-access notice.
  // 'live': sign-in and Buy Pro are offered. Switch only when the app, billing (multi-plan) and the production payment switch are approved and deployed.
  launchState: 'preview',
  domain: 'riksora.com',              // owner's domain (2026-11-16)
  business: {
    publicName: 'RIKSORA Labs',        // nama yang tampil di situs (owner memilih tidak menampilkan nama pribadi; identitas pemilik hanya untuk dokumen Midtrans)
    legalForm: 'Perorangan',          // usaha perorangan (belum terdaftar sebagai badan usaha)
    address: 'Majalengka, Jawa Barat, Indonesia',   // alamat yang boleh tampil (owner memilih tingkat kota)
    email: 'risoralabs@gmail.com',    // email dukungan (owner, 2026-11-16)
    phone: null,                      // opsional: nomor telepon / WhatsApp dukungan (belum ada)
    supportHours: null,               // mis. 'Senin-Jumat 09.00-17.00 WIB'
    responseTime: null,               // mis. 'maksimal 2 hari kerja'
    nib: null,                        // opsional; tampil bila diisi
  },
  pro: {
    // The prices a customer ACTUALLY pays (owner decision 2026-11-16): Rp 87.000 per month, Rp 400.000 per year. Any Midtrans promotion is applied at checkout
    // by Midtrans and is not advertised here as a "regular price". The server plans must equal these prices (checked by the release gate).
    monthly: {priceIdr: 87000, periodDays: 30},
    yearly: {priceIdr: 400000, periodDays: 365},
    promo: {monthlyIdr: null, yearlyIdr: null, startsOn: null, endsOn: null},   // optional dated promotion shown on the site (off)
    taxNote: null,                    // mis. 'Harga sudah termasuk PPN' | 'Harga belum termasuk PPN'
    autoRenew: false,                 // implementasi saat ini: pembelian sekali bayar per periode, tidak diperpanjang otomatis
  },
  payment: {
    provider: 'Midtrans',
    methods: null,                    // metode yang benar-benar diaktifkan di akun Midtrans, mis. ['QRIS','Transfer bank (Virtual Account)','E-wallet','Kartu']
  },
  refund: {
    windowDays: 7,                    // diserahkan owner kepada Claude (2026-11-16); ubah di sini bila ingin lain
    conditions: 'Pro belum dipakai untuk membuat Sesi di luar kuota Free sejak pembayaran; pembayaran ganda atau Pro yang tidak aktif setelah pembayaran lunas dikembalikan penuh',
  },
  legalApproval: {                    // diisi owner setelah teks ditinjau (penasihat hukum disarankan); tanggal ISO, mis. '2026-12-01'
    terms: null, privacy: null, refund: null,
  },
  lastUpdated: '2026-11-16',
};
