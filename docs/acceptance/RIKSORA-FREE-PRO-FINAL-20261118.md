# Free dan Pro: laporan akhir (2026-11-18)

Label: semua bukti di sini SYNTHETIC / QA, di host lokal. Tidak ada data pasar nyata, tidak ada pembayaran produksi, dan tidak ada persetujuan hukum yang sudah diberikan.

## Aturan produk (keputusan owner 2026-11-18)

- **Free:** paling banyak satu Sesi baru per hari UTC. Setiap hari UTC paling banyak satu bulan historis baru diaktifkan. Di dalam bulan yang sudah diaktifkan, trade tidak dibatasi. Sesi di dalam bulan boleh dilanjutkan. Setelah akhir bulan, replay tidak dapat dilanjutkan, trade baru tidak dapat dibuka, dan Jump tidak dapat dipakai. Posisi terbuka tetap terbuka dan dapat ditutup manual. Hasil dan statistik tetap dapat dilihat. Kuota diperbarui 00.00 UTC (07.00 WIB).
- **Pro:** Sesi baru dan bulan data tanpa batas selama paket aktif. Satu Sesi dapat dilanjutkan melewati batas bulan tanpa membuat Sesi baru.

## Yang sudah diubah dan diuji

| Area | Perubahan | Bukti |
|---|---|---|
| Jump setelah akhir bulan Free | Ditolak untuk semua posisi, dengan atau tanpa PENDING (`cloud/window_guard.py`) | `tests.test_window_guard` 5/5 OK |
| Jump di dalam bulan Free | Dibatasi ke akhir bulan, tanpa PENDING pun (`execution/research.py`). Tidak ada perubahan reducer | `tests.test_window_jump` 8/8 OK, `tests.test_window_jump_recovery` 7/7 OK (termasuk SIGKILL) |
| Kuota dan batas bulan Free | Sudah ada, tidak diubah | `tests.test_free_pro_months` 7/7 OK, termasuk Sesi kedua di hari UTC yang sama ditolak dan Sesi lama tetap bisa dibaca |
| Pro lintas bulan | Sudah ada (Jan–Mar dan Des→Jan di QA) | `tests.test_free_pro_months` (Pro tiga bulan dengan restart) OK |
| Syarat bagian 4 dan halaman harga | Diperbarui sesuai aturan di atas | `npm run build:release` OK, `test:site` OK, `test:account-plan` OK, lint OK |
| Pesan batas di frontend | Tidak lagi menjanjikan Jump setelah batas | `frontend/src/tickAlpha/accountClient.js` |

Catatan: `cloud/research.py` dan `cloud/research_v2.py` berisi perubahan (guard `SET_METHOD`, SEEK di batas) yang bukan dibuat dalam pekerjaan ini. Perubahan itu tidak dibatalkan dan tidak di-commit di sini.

## Siap produksi (dalam batas QA ini)

- Kuota Free harian dan aktivasi bulan per hari UTC.
- Batas bulan Free: replay, Jump, OPEN, dan API tidak bisa melewati akhir bulan.
- Posisi terbuka di akhir bulan tidak ditutup atau diubah oleh sistem.
- Kelanjutan Pro lintas bulan, dengan parity dan restart.

## Belum tersedia (tidak dijanjikan di Syarat atau halaman harga)

1. **Pair dan metode terikat pada satu Sesi (aturan produk, keputusan owner).** Untuk mengganti pair atau metode, pengguna keluar dari Sesi. Sesi yang sudah ada tetap tersimpan dan dapat dilanjutkan kembali. Aturan ini sudah ditulis di Syarat bagian 4. Pekerjaan multi-pair dalam satu Sesi (F3) tidak lagi dibutuhkan untuk aturan ini.
   - **Keputusan owner (2026-11-18):** kontrol ganti metode di dalam sesi **dihapus** dari TickAlpha (`frontend/src/tickAlpha/TickAlpha.jsx`). API `SET_METHOD` ditolak dengan kode `METHOD_CHANGE_REQUIRES_NEW_SESSION` (`backend/cloud/research.py`). Reducer engine tidak diubah, dan tes reducer tetap memakai jalur itu.
   - **Keputusan owner:** pair atau metode lain dipakai dengan **membuka Sesi baru**, yang memakai kuota Sesi harian Free.
   - **Catatan:** pembuatan sesi multi-metode (`methodIds`) masih ada. Konsolnya di MI (QA saja) juga masih punya pemilih metode. Keduanya tidak berpengaruh ke jalur produk, tapi perlu diputuskan kalau mau dibersihkan.
3. **Kelanjutan Pro satu tahun penuh di produksi.** Baru diuji lintas Jan–Mar dan Des→Jan. Satu tahun penuh belum diuji (F1).
4. **Kapasitas di atas 20 trader.** 40 trader belum lulus (lihat `RIKSORA-CAPACITY-20261118.md`).
5. **Margin.** Hanya informasional. Keputusan owner masih dibutuhkan.

## Keputusan owner yang masih diperlukan

- Persetujuan ulang Syarat dengan tanggal (lihat `RIKSORA-LEGAL-REAPPROVAL-20261118.md`).
- Izin publikasi ke riksora.com.
- Metode pembayaran Midtrans yang aktif (sudah diisi sementara, perlu dicocokkan dengan dashboard).
- Push dan CI (sanitasi atau tidak).
- Margin dan multi-pair.
