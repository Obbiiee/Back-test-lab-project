# Persetujuan ulang teks hukum (2026-11-18)

Status: **MENUNGGU PERSETUJUAN OWNER.** Claude tidak mengubah `legalApproval` di `frontend/src/site/siteConfig.js`. Tanggal persetujuan hanya boleh diisi setelah owner menyetujui sendiri.

## Teks Syarat bagian 4 yang akan disetujui (sesuai keputusan owner 2026-11-18)

Versi yang disetujui 2026-11-17 menyebut kuota Free per bulan kalender. Versi ini menggantikannya:

> 4. Paket Free dan Pro
> - Free: paling banyak satu Sesi baru per hari UTC.
> - Setiap hari UTC, paling banyak satu bulan historis baru dapat diaktifkan. Di dalam bulan yang sudah diaktifkan, tidak ada batas jumlah trade.
> - Sesi yang belum mencapai akhir bulan historisnya dapat dilanjutkan. Setelah akhir bulan, replay tidak dapat dilanjutkan dan trade baru tidak dapat dibuka. Posisi yang masih terbuka tetap terbuka dan dapat Anda tutup secara manual; hasil dan statistik tetap dapat dilihat.
> - Kuota diperbarui pukul 00.00 UTC (07.00 WIB). Kuota pembuatan Sesi, kuota aktivasi bulan historis, dan hak melanjutkan Sesi adalah tiga hal yang berbeda.
> - Pro: Sesi baru dan bulan data tanpa batas selama paket aktif. Satu Sesi Pro dapat dilanjutkan melewati batas bulan tanpa membuat Sesi baru.
> - Pro dibeli per periode, tidak diperpanjang otomatis, dan aktif sampai masa berlakunya habis. Harga dan periode tercantum di halaman Harga.

Yang **tidak** dinyatakan di Syarat maupun halaman harga (belum lulus QA):
- Ganti pair di dalam satu Sesi.
- Ganti metode di dalam satu Sesi.
- Kelanjutan satu Sesi Pro selama satu tahun penuh (baru diuji lintas Jan–Mar dan Des→Jan, bukan satu tahun di produksi).

## Yang harus dilakukan owner

1. Baca teks di atas dan halaman `/terms` serta `/pricing` di situs.
2. Jika setuju, balas di chat dengan kata "setuju" dan tanggal (misalnya "setuju 2026-11-18").
3. Setelah itu, `legalApproval.terms` diisi tanggal tersebut dan `npm run build:release` dijalankan ulang. Gerbang rilis hanya memeriksa bahwa tanggal ada, bukan isi teksnya.

## Kebijakan Privasi dan Pengembalian Dana

- Privasi (`legalApproval.privacy`): tidak ada perubahan yang menyentuh isinya.
- Pengembalian Dana (`legalApproval.refund`): kondisinya menyebut "Pro belum dipakai untuk membuat Sesi di luar kuota Free". Kalimat ini masih konsisten, tapi owner perlu menilai ulang.
