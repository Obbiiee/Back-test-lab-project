# Usulan: jalan ke target 500 MB per Session (review kontrak persistensi)

Status: USULAN, belum disetujui pemilik. Tidak mengubah kontrak, kode, atau data apa pun. Semua angka di bawah dikutip dari
dokumen repo (CP2, CP4, CP6A-9, freeze register 2026-11-08), bukan ukuran baru, kecuali disebut lain.

## 1. Temuan utama: kontrak yang dikhawatirkan sudah ada

Kekhawatiran awal ("perlu skema bukti blok yang lebih ringkas") sebagian besar sudah dijawab repo sendiri:

| Mode | Isi log durable per Session | Ukuran terukur |
|---|---|---|
| `session-log-v2` (salinan timeline) | posisi + advance per grup | 84,5 MB per 137 ribu grup (satu hari XAU) |
| `shared-source-v1` | hanya rantai advance/kursor | 434 KB per hari, kira-kira 178 MB per tahun (proyeksi linear CP6A-9) |
| `shared-source-v2` | checkpoint `nextPosition`, tanpa log posisi/advance per grup | belum diukur di dokumen yang saya baca |

`AdmittedObservedSource` di `backend/execution/historical.py` sudah berdefault `shared-source-v2`. Freeze register
(2026-11-08) menyebut celahnya: `ObservedCatalog.resolve` tidak meneruskan mode, jadi jalur produk bisa tetap jatuh ke
`session-log-v2`. Itu harus diverifikasi di kode cabang produk, bukan diasumsikan.

Konsekuensi untuk pekerjaan saya sebelumnya: codec `zlib-1` default baru hanya menolong jalur `session-log-v2`. Kalau
produk memang memakai `shared-source-v2`, manfaatnya kecil. Itu tetap aman (tidak mengubah byte logis), tetapi jangan
dihitung sebagai jalan ke 500 MB.

## 2. Dari mana sisa 4,45 GB per tahun (proyeksi CP6A-9) berasal

Timeline bukan lagi pos terbesar. CP6A-9 menyebut 4,45 GB non-timeline per tahun, dan CP2 menunjukkan baris PostgreSQL
sekitar 5 KB per command ADVANCE (5.818 B tuple, 14.564 B teralokasi termasuk indeks). `replay_to` menyimpan banyak
command ADVANCE kecil. Tuas terbesar karena itu:

1. **Gabung ADVANCE.** Satu command per rentang yang dikonfirmasi, bukan per langkah kecil. Kontrak acknowledgement
   tetap per rentang; yang berubah hanya granularitas penyimpanan. Perlu keputusan pemilik karena menyentuh semantik
   idempotensi retry.
2. **Arsip order tertutup.** Freeze register sendiri menyebut "normal-session closed order archive" belum ada.
   Order tertutup dipadatkan ke satu objek terkompresi per bulan, indeks tetap di PostgreSQL.
3. **Checkpoint periodik, bukan per command.** "Periodic compact recovery bases" juga tercatat belum ada.
4. **Kompresi payload PostgreSQL.** CP2 mengukur penghematan payload 57,64% pada 10 baris kecil, tetapi selisih
   database hanya 0,32%. Tidak layak sendirian; berguna hanya setelah poin 1-3 mengurangi jumlah baris.

## 3. Tahapan yang diusulkan (masing-masing berhenti untuk review pemilik)

1. **Pastikan mode produk.** Tes kecil: jalankan satu hari sintetis lewat `ObservedCatalog.resolve` dan baca
   `storage_mode` yang terpakai. Hasil: ya/tidak jalur produk memakai `shared-source-v2`. Tidak mengubah kode produk.
2. **Ukur v2 nyata satu hari.** Pakai runner `tests.qa_historical_day_v2` (butuh PostgreSQL dan data H1; tidak ada di
   mesin ini). Keluarannya mengganti proyeksi linear 178 MB dengan angka v2.
3. **Rincian byte per tabel.** `tick_commands`, `tick_events`, `tick_checkpoints`, ditambah indeks, dibagi per jenis
   command. Itu menentukan apakah poin 1 atau 2 di bagian 2 yang menang.
4. **Prototipe gabung ADVANCE di cabang terpisah** dengan tes parity terhadap hash event dan saldo, serta tes
   idempotensi retry dan kematian proses (tes PostgreSQL yang sudah ada).

## 4. Yang tidak diusulkan

- Mengubah kontrak no-look-ahead atau rantai hash.
- Mengaktifkan `delta-dict-zlib-1` (hemat 19,65% blok, baca 2x lebih lambat, 0% ukuran file di sampel CP4).
- Mengklaim target 500 MB tercapai. Belum ada ukuran tahunan nyata di repo; semua adalah proyeksi linear.

## 5. Keterbatasan

Saya tidak punya PostgreSQL, data H1, atau VPS QA di mesin ini, jadi tahap 1-3 belum bisa saya jalankan dan angka di
atas tidak diverifikasi ulang. Dokumen CP6A-9 yang saya kutip adalah ringkasan, bukan bukti mentah.
