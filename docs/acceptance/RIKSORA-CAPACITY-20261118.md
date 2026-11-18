# Kapasitas produk, hasil tes sintetis (2026-11-18)

Label: SYNTHETIC / TEST ONLY, di satu host lokal. Bukan kapasitas VPS dan bukan produksi. Generator beban berjalan di host yang sama dalam cgroup terpisah (kontensi nyata). Anggaran: cgroup 5 vCPU / 14 GiB, pelindung OS (MemAvailable >= 1 GiB, tanpa swap, disk bebas >= 30 GB, CPU host > 97 % selama 10 detik).

## Hasil

| Tes | Trader | Worker | Selesai | Gagal | Gerbang | Catatan |
|---|---|---|---|---|---|---|
| Prasyarat | 1 × 262.144 tick | 4 | 1/1 | 0 | tidak terpicu | parity true, 37 job SUCCEEDED |
| Kapasitas | 20 × 262.144 tick | 3 (setelan produksi) | **20/20** | 0 | tidak terpicu | CPU host puncak 78,1 %, MemAvailable terendah 12,68 GiB, queue wait p95 4,1 s, p99 6,9 s, end-to-end p95 528 s, journal p50 sekitar 10 s |
| Kapasitas | 40 × 262.144 tick | 3 | **8/40** | 32 | tidak terpicu | CPU host puncak 92 %, queue wait p50 41 s, p95 51 s, max 59 s (TTL 60 s) |

## Penyebab kegagalan 40 trader

1. **Token login kedaluwarsa (harness, bukan produk):** 32 trader gagal dengan `401 Unauthorized` saat polling. Token berlaku 1.800 detik, dan harness tidak memperbarui login untuk run yang lebih panjang. Harness perlu diperbaiki sebelum angka 40 bisa dinilai adil.
2. **Antrean kewalahan (kemungkinan nyata):** dengan 3 worker, queue wait sudah mendekati TTL 60 detik. Lima job replay kedaluwarsa di antrean dan berstatus `RECONCILE_REQUIRED`. Itu perilaku fail-closed yang diizinkan, tapi berarti beban 40 trader melewati kapasitas antrean pada konfigurasi ini.

## Yang belum diuji

- Tangga 60, 80, 100 trader.
- Sustained minimal 15 menit pada kapasitas stabil tertinggi.
- Perbandingan 3 vs 4 vs 6 slot.
- Latensi journal dan export (perlu profil satu panggilan di jalur indeks).

## Biaya per trader

Rp 270.000 / 20 trader lulus = **Rp 13.500 per trader per bulan**. Ini **hipotesis**: 20 trader lulus pada satu run, belum sustained 15 menit, dan belum di host produksi.
