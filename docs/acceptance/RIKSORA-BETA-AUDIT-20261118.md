# Audit sebelum publikasi Beta (2026-11-18)

Label: kode dan tes lokal, bukan kapasitas atau produksi. Tidak ada kode yang diubah dalam audit ini, kecuali penanda persetujuan Syarat di `siteConfig.js`.

## Status publikasi: DITAHAN

Pemeriksaan kritis gagal. Syarat bagian 4 menjanjikan aturan yang belum berlaku di API yang sedang tayang di riksora.com:

- API tayang (`deploy/site/app_api.py`) dimulai pukul 05:11 UTC. Perubahan aturan batas bulan dan penolakan `SET_METHOD` dibuat pukul 12:56–15:48 UTC, jadi API tayang belum memakainya.
- Akibatnya, di produksi posisi ACTIVE Free masih bisa lewat Jump melewati akhir bulan. Syarat menyatakan hal itu tidak boleh terjadi.
- Ganti metode di sesi multi-metode masih diterima API tayang.

Yang diperlukan sebelum publikasi: restart API dari kode yang sudah di-commit (perlu persetujuan owner untuk deploy backend), lalu smoke test, baru `publish.sh`. Perubahan di working tree juga berisi pekerjaan yang bukan dari pekerjaan ini (`cloud/research.py` dan `cloud/research_v2.py`), dan perlu diputuskan apakah ikut di-commit.

## Jawaban per pertanyaan

### 1. Free: lanjut ke Februari dalam sesi yang sama setelah reset?

**Tidak.** Ini sesuai aturan produk.
- Sesi dikunci ke bulan awal (`startPeriod`) saat dibuat. Jendelanya adalah bulan itu (`month_bounds`).
- Setelah akhir Januari, ADVANCE dan Jump ke Februari ditolak (`WINDOW_BOUNDARY`, `WINDOW_ENDED_CONTINUATION_ONLY`, `WINDOW_COMPLETED`).
- Februari hanya bisa dipakai lewat Sesi baru. Itu memakai kuota Sesi harian dan kuota aktivasi bulan harian, yang dihitung terpisah di `cloud/entitlements.py` (kunci `SESSION` dan `WINDOW`).

Bukti: `tests.test_free_pro_months` (`test_free_session_stops_at_the_end_of_its_month_without_touching_orders`, `test_window_quota_is_one_new_month_per_utc_day_and_reuse_is_free`) 7/7 OK, dan `tests.test_window_guard` 5/5 OK pada kode terbaru.

### 2. Posisi OPEN dan PENDING saat jendela berakhir

- **Tidak ditutup otomatis.** Tes: `test_window_guard`, `test_window_jump`, `test_window_jump_recovery` (SIGKILL) OK.
- **Tick di luar jendela:** di dalam bulan, Jump sekarang dibatasi ke akhir bulan, dengan atau tanpa PENDING (`execution/research.py`). Setelah akhir bulan, Jump ditolak (`cloud/window_guard.py`). Ini kode baru; belum tayang di API produksi.
- **PENDING:** tidak terpicu setelah batas. Jump ditolak dengan `PENDING_AT_WINDOW_END`, dan order boleh dibatalkan.
- **CLOSE tidak mengeksploitasi harga masa depan.** Ini hasil pembacaan kode:
  - CLOSE membuat `EXIT_REQUESTED` dengan `availableNs` = cursor saat ini (`execution/engine.py`, baris 94).
  - Fill terjadi pada tick pertama setelah cursor, dan hanya saat engine maju.
  - Free tidak bisa maju setelah batas, jadi fill tidak pernah terjadi. Tidak ada harga masa depan yang terpakai.

**Ketidaksesuaian (perlu keputusan owner):**
- Setelah batas, CLOSE diterima tapi tidak pernah dieksekusi. Posisi tetap ACTIVE dengan permintaan menggantung.
- END kemudian menandai posisi ACTIVE menjadi `UNRESOLVED_SESSION_END_ACTIVE` (`execution/engine.py`, baris 104–112). Ini perubahan state finansial, dan pengguna tidak diberi tahu dengan jelas.
- Rekomendasi: pilih satu:
  - (a) Tolak CLOSE setelah batas dengan pesan jelas. Posisi tetap ACTIVE, dan pengguna tahu harus menunggu bulan baru.
  - (b) Eksekusi CLOSE pada quote terakhir yang sudah terlihat. Ini mengubah semantik fill, jadi perlu persetujuan owner dan tes finansial baru.
- Tidak saya ubah, karena menyentuh engine finansial.

**Kesinambungan saat jendela berikutnya:** posisi tetap di Sesi lama dan tidak ikut ke Sesi baru. Belum ada tes khusus untuk ini.

### 3. Multi-pair dan ganti metode

- Tidak ada klaim di Syarat, halaman harga, atau landing yang menyatakannya tersedia. Syarat bagian 4 hanya menyatakan bahwa pair dan metode terikat pada satu Sesi.
- Kontrol ganti metode di TickAlpha sudah dihapus di kode (belum tayang). API tayang masih menerima `SET_METHOD`.

## Celah tes

- Belum ada tes CLOSE setelah batas (apakah posisi tetap ACTIVE dan tidak terisi).
- Belum ada tes kesinambungan posisi saat jendela berikutnya diaktifkan.
- Belum ada tes Jump ke bulan berikutnya di API yang berjalan (karena API tayang belum memuat perubahan).

## Rekomendasi minimal

1. Putuskan perilaku CLOSE setelah batas (a atau b di atas).
2. Commit backend yang sudah diuji, lalu restart API dengan persetujuan owner, dan jalankan smoke test untuk Jump setelah batas dan `SET_METHOD`.
3. Tambahkan dua tes yang belum ada.
4. Baru lakukan `publish.sh`, dengan rollback tersedia (`~/site/dist.prev`).

## Status rilis (2026-11-18)

- Commit rilis: `090bad5` (lokal, belum di-push). Berisi perubahan backend yang diaudit dan diuji. `research_v2.py` sengaja tidak ikut.
- Worktree siap: `~/releases/riksora-090bad5` (rilis) dan `~/releases/riksora-c82bd85` (rollback). Keduanya bersih.
- Produksi: job durable tidak ada yang berjalan (11 job, semua SUCCEEDED), sehingga restart tidak memutus pekerjaan.
- **Restart API: SELESAI** (proses baru dari `~/releases/riksora-090bad5`, port 8010 mendengarkan). Preflight lulus: 0 job QUEUED/RUNNING, tidak ada koneksi aktif ke 8010, tidak ada benchmark, dan rilis tidak mengubah skema.
- **Smoke test tanpa login: PASS.** Password endpoint tidak terbuka di jalur publik (404). `/api/v1/workspaces` tanpa login 401. Jalur yang ditutup 404. `/api/v1/auth/providers` masih 200 (catatan: `prune` tidak membuangnya, tapi Caddy memang mengizinkan `/api/v1/auth/*`).
- **Belum dijalankan: publikasi, dan smoke test dengan login Google** (kuota Free, guard window, CLOSE setelah batas, SET_METHOD, Jump, resume, Journal, Analytics, idempotensi). Ini hanya bisa dijalankan lewat browser oleh owner.

Langkah restart (setelah persetujuan dan akun uji):
1. Buat drop-in `~/.config/systemd/user/riksora-api.service.d/release.conf` dengan `ExecStart=` kosong lalu `ExecStart=%h/tools/venv313/bin/python %h/releases/riksora-090bad5/deploy/site/app_api.py`.
2. `systemctl --user daemon-reload && systemctl --user restart riksora-api`.
3. Verifikasi `/proc/<pid>/cwd` mengarah ke worktree rilis, lalu jalankan smoke test.

Rollback: hapus drop-in, ganti `riksora-090bad5` dengan `riksora-c82bd85` di `release.conf`, `daemon-reload`, `restart`.
