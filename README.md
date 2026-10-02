# Backtest Lab

## Versi utama

Sumber aplikasi utama berada di `frontend/src/FigmaWorkspace.jsx`, dimuat melalui
`frontend/src/main.jsx`. Stack: React, Vite, dan TradingView Lightweight Charts.

Arsip XAUUSD 10 tahun berada di `frontend/public/market/decade/`: 3.486.461 candle
M1 dari 2 Oktober 2016 hingga 25 September 2026 UTC. File intraday dimuat bertahap
saat chart digeser ke kiri. Lihat `docs/HISTORICAL_XAU.md` untuk sumber dan batasan data.

Folder `legacy/` menyimpan versi terdahulu dan snapshot sumber sebelum perubahan
drawing. Folder tersebut bukan entrypoint aplikasi utama. Adapter drawing open-source
sudah ada dalam sumber, tetapi integrasinya ke chart belum selesai.

## Menjalankan versi utama

    cd frontend
    npm ci
    npm run dev

Buka alamat lokal yang ditampilkan Vite. Versi utama memuat arsip historis dari
folder public dan menjalankan simulasi di browser; backend tidak diperlukan untuk
alur ini. Harga live memerlukan koneksi internet ke penyedia data.

## Memeriksa frontend

    cd frontend
    npm run build
    npm run test:market
    npm run test:drawings
    npm run test:trading

Lihat docs/ROADMAP.md untuk rencana kerja.

## Menjalankan tes backend (tanpa install apa pun)
    cd backend
    python -m unittest discover -s tests -t . -v

## Menjalankan API
    cd backend
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    uvicorn api.main:app --reload --port 8000
Lalu buka http://127.0.0.1:8000/docs

## Menjalankan alur lama yang memakai API
Jalankan API di satu terminal, lalu buka terminal kedua:

    cd frontend
    npm install
    npm run dev

Buka alamat yang ditampilkan Vite (biasanya http://localhost:5173). API port 8000
digunakan oleh implementasi lama `frontend/src/App.jsx`; entrypoint saat ini memakai
versi utama yang dijelaskan di atas.
