// Business facts the OWNER must supply before a public release. Nothing here is invented: every value starts as null and the release gate
// (scripts/verify-site-config.mjs, run by `npm run build:release`) refuses to build while any required value is missing or any legal text is unapproved.
// Prices must equal the server plan (BTL_BILLING_AMOUNT_IDR / BTL_BILLING_DURATION_SECONDS); the same release checklist compares them.
export const SITE = {
  brand: 'RIKSORA Backtest Lab',
  domain: null,                       // e.g. 'riksora.example'  (public https domain)
  business: {
    legalName: null,                  // nama usaha / nama pemilik sesuai dokumen Midtrans
    legalForm: null,                  // 'Perorangan' | 'CV' | 'PT' ...
    address: null,                    // alamat lengkap yang boleh ditampilkan
    email: null,                      // email dukungan
    phone: null,                      // nomor telepon / WhatsApp dukungan
    supportHours: null,               // mis. 'Senin-Jumat 09.00-17.00 WIB'
    responseTime: null,               // mis. 'maksimal 2 hari kerja'
    nib: null,                        // opsional; tampil bila diisi
  },
  pro: {
    priceIdr: null,                   // integer Rupiah per periode, mis. 99000
    periodDays: null,                 // lama satu periode Pro dalam hari, mis. 30
    taxNote: null,                    // mis. 'Harga sudah termasuk PPN' | 'Harga belum termasuk PPN'
    autoRenew: false,                 // implementasi saat ini: pembelian sekali bayar per periode, tidak diperpanjang otomatis
  },
  payment: {
    provider: 'Midtrans',
    methods: null,                    // metode yang benar-benar diaktifkan di akun Midtrans, mis. ['QRIS','Transfer bank (Virtual Account)','E-wallet','Kartu']
  },
  refund: {
    windowDays: null,                 // jendela pengembalian dana dalam hari (keputusan owner)
    conditions: null,                 // syarat pengembalian dana (keputusan owner), teks pendek
  },
  legalApproval: {                    // diisi owner setelah teks ditinjau (penasihat hukum disarankan); tanggal ISO, mis. '2026-12-01'
    terms: null, privacy: null, refund: null,
  },
  lastUpdated: '2026-11-16',
};
