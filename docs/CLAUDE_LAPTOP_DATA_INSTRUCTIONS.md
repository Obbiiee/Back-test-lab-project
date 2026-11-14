# Instruksi untuk Claude di laptop: menyiapkan data tick dan OHLC untuk VPS RIKSORA

Dokumen ini untuk Claude yang punya akses ke data di laptop owner (HistData-UTC zip, Dukascopy CSV, parquet kompak). Tujuannya: menyiapkan data dalam bentuk
yang PERSIS diterima kode di repo ini, lalu mengirimnya ke VPS. Ikuti urutan di bawah. Jangan menebak format; semua aturan di sini berasal dari kode
(`backend/market_data/compact_tick.py`, `backend/tools/claude_exp/convert_*.py`, `backend/tools/claude_exp/ohlc/engine.py`).

Branch kerja: `claude/dual-engine-v1-20261114`. Tidak ada force-push, tidak ada merge ke main, tidak ada kunci (Google/Midtrans/R2) di chat atau repo.

## 1. Status hak data (wajib dicatat)
Data HistData/Dukascopy yang dimiliki owner berstatus rights = UNKNOWN. Artinya: hanya untuk QA privat di VPS, tidak boleh dipakai sebagai bukti komersial,
tidak boleh dipublikasikan, tidak boleh masuk Git. Konverter di repo sudah menulis `rights = {class: UNKNOWN}` ke manifest; jangan mengubahnya.
Produk menolak sumber nyata tanpa bukti hak yang dipin (`BTL_MONTHLY_PARQUET_CATALOG`), jadi data ini dipakai lewat jalur QA privat, bukan jalur produk publik.

## 2. Spesifikasi VPS (tujuan)
- 6 vCPU AMD EPYC, 15,6 GiB RAM, tanpa swap, disk 200 GB (sekitar 176 GB kosong), Ubuntu 24.04, tanpa sudo.
- Toolchain user-space: Python 3.13 (`~/tools/venv313`), PostgreSQL 17, Node 22. NumPy 2.5.4, PyArrow 26.0.0 (versi yang sama dipakai di laptop bila memungkinkan).
- Folder tujuan: `/home/developer/data/incoming/` (belum ada, buat dengan `mkdir -p`). Jangan menaruh data di dalam folder repo.
- Anggaran penyimpanan (ukur ulang dari `catalog.json`; ini perkiraan):
  - tick kompak: sekitar 20-30 MB per pair-bulan (data sintetis kami: 19,4 byte per tick; 1,44 juta tick per bulan = sekitar 28 MB). 16 pair x 34 bulan = sekitar 15 GB.
  - OHLC sembilan timeframe: sekitar 1,1 MB per pair-bulan (diturunkan di VPS, tidak perlu dikirim) = sekitar 0,6 GB.
  - ruang kosong yang harus dijaga: gerbang proyek meminta disk bebas >= 30 GB.
- Konversi sebaiknya dilakukan di LAPTOP (bukan VPS) supaya CPU VPS tidak terpakai; VPS hanya menerima hasil jadi dan memverifikasinya.

## 3. Format tick yang diterima (compact tick, artefak `BTL-COMPACT-TICK-1`)
Satu dataset = satu pair satu bulan (konvensi konverter). Isinya `compact.json` (manifest) dan satu file parquet per bulan UTC: `<YYYY-MM>/ticks.parquet`.
Kolom parquet (semua non-null):

| Kolom | Tipe | Arti |
|---|---|---|
| `ts_ns` | int64 | waktu UTC dalam nanodetik sejak epoch |
| `bid` | int64 | harga bid sebagai bilangan bulat berskala (scale ada di manifest) |
| `ask` | int64 | harga ask, sama |
| `ordinal` | int64 | urutan baris sumber, naik tegas (bukan urutan venue yang dipercaya) |
| `is_crossed` | bool | `ask < bid` (dicatat, tidak dibuang) |
| `group_id` | int64 | tick dengan timestamp sama berbagi group (atomik) |

Aturan yang ditegakkan penulis (jika dilanggar, penulisan gagal; jangan akali):
- Harga ditulis sebagai teks desimal eksak dari sumber (`^[0-9]+(\.[0-9]+)?$`), tidak boleh float biner, tidak boleh dibulatkan. Jika ada presisi lebih dari scale, naikkan scale (konverter mencoba scale + 1, maksimal 18). Contoh scale: EURUSD 5, USDJPY 3, XAUUSD 3.
- Timestamp tidak boleh mundur (non-decreasing). Timestamp sama boleh ada (tie), tetap dalam urutan sumber. JANGAN mengurutkan ulang, JANGAN menghapus duplikat, JANGAN interpolasi, JANGAN membuat tick dari candle.
- `ordinal` naik tegas dari 0.
- Waktu harus UTC. Sumber HistData "UTC" langsung pakai; jika sumber memakai zona lain (mis. EST tanpa DST), konversikan secara eksplisit dan catat, jangan campur.
- Harga harus > 0. Quote crossed (ask < bid) dibiarkan dan dihitung di manifest.
- Dataset punya identitas: `datasetId` (mis. `local:histdata-utc:EURUSD:2026-05:<hash>`) dan `datasetVersion` (64 hex). Konverter membuatnya dari hash sumber; jangan diubah manual.
- Output tidak boleh menimpa dataset yang sudah ada (immutable). Jika perlu ulang, tulis ke folder baru.

### Perintah yang sudah ada (jalankan di laptop, dari folder `backend/`)
HistData-UTC (zip bulanan `HISTDATA_UTC_<PAIR>_T<YYYYMM>.zip`, header `timestamp,bid,ask`, timestamp milidetik):
```
python tools/claude_exp/convert_histdata_compact.py --src "<folder HistData-UTC>" --out "<folder keluaran>" --workers 3 --pairs EURUSD,GBPUSD
```
Dukascopy CSV (dukascopy-node, `timestamp,askPrice,bidPrice,askVolume,bidVolume`), satu bulan per CSV:
```
python tools/claude_exp/convert_dukascopy_month.py --csv usdcad_2026-07.csv --pair USDCAD --month 2026-07 --zip-out "<folder zip>" --out "<folder keluaran>"
```
Konverter bersifat resumable dan hanya membaca sumber. Setiap bulan diverifikasi setelah ditulis (hash manifest, SHA-256 per file, pemeriksaan dalam, jumlah baris harus sama dengan sumber)
dan hasilnya masuk `catalog.json` (jumlah baris, byte, hash manifest, SHA-256 zip sumber, jumlah crossed quote).

Sumber lain (CSV lain, tick Exness, dll.): jangan menulis konverter baru tanpa memberi tahu; bentuknya harus menghasilkan peristiwa `{timeNs, bid, ask, rawOrdinal}` dan memanggil `write_compact(root, events, parent=dict(datasetId=..., datasetVersion=...), scale=...)`. Laporkan dulu format sumbernya.

## 4. OHLC
Ada dua jalur, pilih sesuai ketersediaan tick:
- JALUR A (utama, tidak perlu mengirim OHLC): untuk periode yang punya tick, kirim tick saja. VPS membuat sembilan timeframe (M1, M3, M5, M15, M30, H1, H2, H4, D1) dari tick dengan
  `engine.publish_month` (harga MID = (bid+ask)/2 per tick, aritmetika bilangan bulat eksak, batas candle UTC, hasil diverifikasi terhadap oracle independen). Objek bersifat immutable dan deterministik.
- JALUR B (prasejarah tanpa tick, mis. 2021-2022, atau sejarah panjang agar D1 punya 5.000 candle, butuh sekitar 19 tahun): importer BELUM ADA di repo. Jika owner punya OHLC saja, kirim
  M1 (paling disukai) atau timeframe asli dengan format ini, dan beri tahu Claude di VPS supaya importer dibuat dulu:
  - CSV atau Parquet UTF-8, kolom: `bar_start_utc_ms` (int, awal bar UTC), `open`, `high`, `low`, `close` (teks desimal eksak, bukan float), `tick_count` (opsional), dan kolom/metadata `price_basis` (BID, ASK, atau MID).
  - Satu pair per file, urut naik, tanpa duplikat, tanpa bar masa depan, batas D1 pukul 00:00 UTC.
  - OHLC bukan otoritas eksekusi: tidak pernah dipakai untuk menyelesaikan trade; hanya tampilan chart, indikator, dan konteks sebelum titik mulai.
  - Peringatan basis: candle dari tick kita berbasis MID. OHLC eksternal berbasis BID tidak identik; di titik sambungan harus diberi label basis yang jelas, jangan dicampur diam-diam.
- Target tampilan: sebelum titik mulai trader (mis. 1 Januari 2026) tersedia sampai 5.000 candle per timeframe, termasuk D1. Candle sesudah titik mulai dibentuk dari tick yang sudah terungkap saja (tanpa lookahead).

## 5. Verifikasi di laptop sebelum mengirim
Untuk setiap dataset: buka dengan `CompactTickReader(folder, expected_manifest_hash=<hash dari compact.json>)` lalu `verify_all(deep=True)`. Laporkan ringkasan per pair-bulan:
jumlah baris, jumlah timestamp group, tie, crossed quote, `firstTimeNs`/`lastTimeNs`, byte, hash manifest, SHA-256 zip sumber, dan celah waktu yang terlihat (akhir pekan normal; celah lain sebutkan).
Jika ada bulan gagal verifikasi atau jumlah baris tidak cocok dengan sumber, jangan dikirim dan jangan "diperbaiki": laporkan apa adanya.

## 6. Mengirim ke VPS
Hasil yang dikirim: folder `<PAIR>/<YYYY-MM>/` (isi: `compact.json`, `<YYYY-MM>/ticks.parquet`, `DONE.json`) dan `catalog.json`. Zip mentah tidak perlu (hash-nya sudah di katalog), kecuali diminta.
```
ssh <alias-vps> "mkdir -p /home/developer/data/incoming"
rsync -avP --partial <folder keluaran>/ <alias-vps>:/home/developer/data/incoming/compact/
```
(`<alias-vps>` diisi owner dari konfigurasi SSH lokal; jangan mencetak atau mengirim kunci/kata sandi ke chat.) Tanpa rsync, `scp -r` juga bisa. Setelah selesai, buat daftar `sha256sum` seluruh file di laptop dan kirim juga supaya VPS bisa mencocokkan.
Kirim bertahap (mis. satu pair dulu, lalu pair berikutnya) dan periksa ruang disk VPS sebelum tiap tahap.

## 7. Yang dilakukan Claude di VPS setelah data tiba
1. Mencocokkan SHA-256, memverifikasi tiap dataset dengan `CompactTickReader.verify_all(deep=True)`.
2. Menjalankan `engine.publish_month` untuk sembilan timeframe, memeriksa hasil terhadap oracle, lalu melaporkan ukuran dan waktu.
3. Memasang store OHLC di folder lokal (SIMULASI R2; R2 sungguhan hanya dengan kredensial yang disuntik owner, tidak lewat chat).
4. Semua hasil diberi label proven / hypothesis / prototype / perlu uji produksi, dan status hak UNKNOWN tetap tertulis di setiap laporan.
