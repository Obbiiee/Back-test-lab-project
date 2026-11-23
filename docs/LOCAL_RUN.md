# Menjalankan RIKSORA di laptop sendiri (dari nol)

Satu perintah menyalakan produk yang sama dengan yang berjalan di server: PostgreSQL pribadi, migrasi, data **sintetis** (bukan data pasar), frontend, API, worker, dan satu akun siap pakai. Tidak ada layanan luar, tidak menyentuh database sistem Anda, dan tidak membutuhkan Google atau Midtrans.

## Windows: pakai WSL2 (Windows native tidak didukung)

Di PowerShell (Administrator), sekali saja: `wsl --install -d Ubuntu`, lalu restart dan buka "Ubuntu". Semua perintah di bawah dijalankan di terminal Ubuntu itu. Kloning repo ke folder Linux (mis. `~/riksora`), bukan ke `C:\`, supaya cepat.

## Prasyarat (Ubuntu / WSL2)

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv postgresql-16 nodejs npm   # Node harus 20+; bila lebih lama, pasang dari nodejs.org atau nvm
git clone https://github.com/Obbiiee/Back-test-lab-project.git riksora
cd riksora
git checkout claude/dual-engine-v1-20261114
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.lock
```

PostgreSQL dari apt tidak perlu dijalankan sebagai service; launcher memakai binary `initdb`/`pg_ctl` miliknya sendiri. Bila tidak ditemukan otomatis: `--pg-bin /usr/lib/postgresql/16/bin`.

## Menyalakan

```bash
python deploy/local/dev_stack.py up
```

Menit pertama membangun semuanya (npm ci, build frontend, data). Setelah itu terminal menampilkan alamat `https://localhost:8443/`, email dan kata sandi akun siap pakai. Browser akan memperingatkan sertifikat self-signed: lanjutkan sekali. Buka alamat itu, tekan Masuk, lalu buat Session pada **Januari 2020** (data sintetis 2020-01-01 s.d. 2020-02-15, satu tick per menit).

Kode verifikasi email untuk pendaftaran lain dicetak di terminal yang sama.

## Opsi berguna

| Opsi | Fungsi |
| --- | --- |
| `--enforce` | Aktifkan aturan Free/Pro seperti produksi (Free: 1 Session baru per hari UTC, satu bulan data). Tanpa opsi ini semua dibuka untuk uji. |
| `--port 8443` / `--pg-port 54460` | Ganti port bila bentrok. |
| `--ticks N` | Jumlah tick sintetis (default 131072). |
| `--workers 2` | Jumlah worker. |
| `--rebuild-frontend` | Paksa build ulang frontend setelah mengubah kode. |
| `--keep-db` | Jangan reset basis data akun. |

Berhenti: Ctrl+C. Mulai lagi: perintah `up` yang sama (cepat, data tidak dibuat ulang).
Hapus semuanya: `python deploy/local/dev_stack.py reset` (hanya folder `.local/dev`; repo tidak disentuh).

## Tes

```bash
cd frontend && npm run lint && npm run test:site        # frontend
cd .. && python -m unittest backend.tests.test_window_guard backend.tests.test_window_jump
```

## Batasan

- Data **sintetis / uji saja**; bukan data pasar, bukan bukti performa trading.
- Login Google dan pembayaran Midtrans tidak aktif secara lokal.
- Daftar tes penuh dan runbook QA ada di `AI_CONTEXT/07_TEST_COMMANDS.md`.
