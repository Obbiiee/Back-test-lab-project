# Menjalankan RIKSORA di laptop sendiri (dari nol)

Satu perintah menyalakan produk yang sama dengan yang berjalan di server: PostgreSQL pribadi, migrasi, data **sintetis** (bukan data pasar), frontend, API, worker, dan satu akun siap pakai. Tidak ada layanan luar, tidak menyentuh database sistem Anda, dan tidak membutuhkan Google atau Midtrans.

## Windows: pakai WSL2 (Windows native tidak didukung)

Di PowerShell (Administrator), sekali saja: `wsl --install -d Ubuntu`, lalu restart dan buka "Ubuntu". Semua perintah di bawah dijalankan di terminal Ubuntu itu. Kloning repo ke folder Linux (mis. `~/riksora`), bukan ke `C:\`, supaya cepat.

## Prasyarat (Ubuntu / WSL2)

```bash
sudo apt update
sudo apt install -y git curl python3.12 python3.12-venv postgresql-16
# Node 22 (versi yang dipakai CI). Jangan pakai `apt install nodejs`: Ubuntu 24.04 hanya menyediakan Node 18, sedangkan Vite 8 butuh Node 20.19+ atau 22.12+.
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
. ~/.nvm/nvm.sh && nvm install 22 && node --version   # harus v22.x
git clone https://github.com/Obbiiee/Back-test-lab-project.git riksora
cd riksora
git checkout main
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.lock
```

PostgreSQL dari apt tidak perlu dijalankan sebagai service; launcher memakai binary `initdb`/`pg_ctl` miliknya sendiri. Bila tidak ditemukan otomatis: `--pg-bin /usr/lib/postgresql/16/bin`.

## Menyalakan

```bash
python deploy/local/dev_stack.py up
```

Menit pertama membangun semuanya (npm ci, build frontend, data). Setelah itu terminal menampilkan alamat `https://localhost:8443/`, email dan kata sandi akun siap pakai. Browser akan memperingatkan sertifikat self-signed: lanjutkan sekali. Buka alamat itu, tekan **Masuk**, lalu masukkan email dan kata sandi yang dicetak terminal. Langkah berikutnya (diverifikasi di browser, 2026-11-25):

1. **Workspace:** pada "Choose a workspace" isi nama (mis. `My lab`), tekan *Create workspace*, lalu klik workspace itu untuk membukanya.
2. **Method:** di *My Methods* tekan *Create your first Method*, beri nama, pilih *Free Style*, tekan *Save Method*.
3. **Session:** tekan *New Session*, lanjutkan 4 langkah wizard (Method, Instrument, Period, Capital), lalu *Create Session* dengan periode **Januari 2020**.
4. Tekan tombol Play. Waktu replay mulai 2020-01-01 00:30 UTC.

Data sintetis, satu tick per menit. Dengan `--ticks` bawaan (131072) cakupannya 2020-01-01 s.d. 2020-04-01; tanggal persisnya selalu dicetak di terminal (mis. `--ticks 65536` berakhir 2020-02-15).

Kode verifikasi email untuk pendaftaran lain dicetak di terminal yang sama.

## Opsi berguna

| Opsi | Fungsi |
| --- | --- |
| `--enforce` | Aktifkan aturan Free/Pro seperti produksi (Free: 1 Session baru per hari UTC, satu bulan data). Tanpa opsi ini semua dibuka untuk uji. |
| `--port 8443` / `--pg-port 54460` | Ganti port bila bentrok. |
| `--ticks N` | Jumlah tick sintetis (default 131072). |
| `--workers 2` | Jumlah worker. |
| `--rebuild-frontend` | Paksa build ulang frontend setelah mengubah kode. |
| `--keep-db` | Biarkan PostgreSQL tetap berjalan saat aplikasi berhenti (data tetap ada di `.local/dev` baik dengan maupun tanpa opsi ini). |

Berhenti: Ctrl+C. Mulai lagi: perintah `up` yang sama (cepat, data tidak dibuat ulang).
Hapus semuanya: `python deploy/local/dev_stack.py reset` (hanya folder `.local/dev`; repo tidak disentuh).

## Tes

```bash
cd frontend && npm run lint && npm run test:site        # frontend
cd ../backend && PYTHONPATH=..:. python -m unittest tests.test_execution_goldens tests.test_error_mapping   # backend, tanpa database
```

## Batasan

- Data **sintetis / uji saja**; bukan data pasar, bukan bukti performa trading.
- Login Google dan pembayaran Midtrans tidak aktif secara lokal.
- Daftar tes penuh dan runbook QA ada di `AI_CONTEXT/07_TEST_COMMANDS.md`.
