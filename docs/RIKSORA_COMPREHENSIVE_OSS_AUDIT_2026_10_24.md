# RIKSORA — audit repository, VPS, workflow dan open-source

Tanggal: 24 Oktober 2026 UTC. Ini laporan bukti dan rekomendasi, bukan authority arsitektur baru atau izin deployment. Authority tetap blueprint dan frozen AI_CONTEXT.

## Keputusan

**GO melanjutkan engine existing secara terisolasi; NO-GO menyebut produk selesai atau merilis historical beta berbayar.** Fondasi cukup baik untuk diteruskan: execution deterministik, batas causal, persistence/idempotency, autentikasi dan adapter pembayaran sudah mempunyai perlindungan nyata. Tidak ada alasan berbukti untuk membangun ulang engine, login atau CRM.

Prioritas owner terbaru: fokus engine dan XAUUSD target 2024–2025; instrumen lain menunggu object storage. Ini tidak menghapus katalog 16 instrumen atau daftar delapan beta sebelumnya. Hanya 22 bulan kandidat numerik, bukan bukti 24 bulan admitted; Oktober tetap ditolak sampai masalah sumber selesai. USDJPY internal untuk konversi tetap diperbolehkan. Izin provider tetap syarat pertama sebelum historical data dipublikasikan.

## Baseline dan batas audit

- Main `62471fa518817598885970993f43d01f53231d97`, checkout functional `b75717201081e6fa2d6fce4f3ea6e83009517dc6`, dan draft Claude `b2018d607d0ae443b5d1062f4a468a57216c1894` dipertahankan.
- PR #2 dan #4–#7 tergabung pada branch functional `2002cedf8b70c659883b6d5a4a7f72ccf7626dc8`; bukan berarti sudah masuk main atau terpasang di VPS.
- Pengujian menyeluruh memakai kandidat terpisah [ba63f070](https://github.com/Obbiiee/Back-test-lab-project/commit/ba63f0709e33a6354998746fcccad91c6ddbbc15), parent 2002ced. Perbedaannya benchmark opsional/tests/docs; aplikasi tetap sama. Kandidat belum diintegrasikan.
- Handoff dasar `a9af8e0fd7405cd27baf50bfca65864aaaefe853`, termasuk arahan cd2bcaa. Laporan ini tidak menggabungkan implementasi ke branch handoff.
- Review upstream mencakup metadata, lisensi, README dan spot-check kode yang relevan; bukan audit keamanan seluruh kode 12 proyek. Tidak ada kode upstream disalin ke aplikasi.

## Temuan prioritas

| Prioritas | Temuan dan implikasi | Tindakan yang disarankan |
| --- | --- | --- |
| P0 | `certifi==2026.7.22` pada lock dan venv aktif terkena advisory kritis GHSA-6q48-6c7w-9gw2. CA intermediates bermasalah bisa memengaruhi TLS outbound pada client yang memakai bundle tersebut. Tidak ditemukan bukti eksploitasi; ini bukan bukti sertifikat HTTPS Caddy bermasalah. | Patch dependency pada kandidat terisolasi ke versi diperbaiki >=2026.10.19, uji outbound OAuth/provider dan regresi; rollout VPS tetap checkpoint tersendiri. |
| P1 | npm audit melaporkan dua package high: Vite8.3.1 dan zod4.6.5; fix8.3.3/4.6.6. Audit production omit-dev nol temuan. | Perbarui dev dependency dan uji build; jangan menyamakan advisory dev server dengan eksploitasi static Caddy. |
| P1 | Frontend aktif `2fba7560385a-claude-ui`, backend launcher release `c370845467608e3d67e74e39b714d501dba7c275`, kandidat source2002ced/ba63 berbeda. | Susun satu release manifest dan kandidat integrasi yang direview sebelum mengklaim keseluruhan runtime sesuai source. |
| P1 | Hak hosted/public HistData belum terbukti, kalender/precision/admission belum tuntas dan Oktober refused. | Inventaris hak, provenance, precision dan coverage; jangan impor massal, menyortir diam-diam atau mengarang gap/fill. |
| P1 | Restore production/offhost dan browser perjalanan pengguna terautentikasi belum dibuktikan saat audit. | Drill pada lingkungan terisolasi serta E2E browser sebelum rollout; unit/native QA tidak menggantikannya. |
| P2 | Tidak ditemukan workflow CI tracked pada baseline yang diaudit; inventory Actions remote tidak berhasil diakses melalui connector. | CI Linux dengan helper SCRAM, override Python, golden vectors, lint/build dan browser gate. |

Advisory primer: [certifi](https://github.com/advisories/GHSA-6q48-6c7w-9gw2), [Vite](https://github.com/advisories/GHSA-rq7h-c2jc-7f22), [Zod](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). Audit dependency tidak membuktikan tidak adanya kerentanan lain. Tidak ada upgrade diterapkan dalam audit ini.

## Engine, autentikasi dan workflow

| Area | Yang sudah baik | Batas yang masih nyata |
| --- | --- | --- |
| Tick/execution | Canonical evidence, exact strings/Fraction, timestamp groups atomic, uncertainty eksplisit; controller memisahkan proposal dari transaksi CAS. Idempotency/revision/receipt persisten. | Tidak boleh mengganti dengan OHLC settlement, mengangkat row order menjadi market sequence atau mengubah frozen kernel demi data yang rusak. Legacy MODELLED tetap jalur terpisah. |
| Statistik | Validasi event chain/genesis/head dan rekonsiliasi state; committed cash curve jujur tanpa unrealized palsu. | MAX_ORDERS128/session, MAX_EVENTS256/command, MAX_ANALYSIS_EVENTS4096 kumulatif; di atas batas analysis UNAVAILABLE. Fork analysis belum tersedia; R0 belum joined dan tidak ada mark-to-market. Tentukan acceptance scope, jangan diam-diam menaikkan kontrak. |
| Google/login | FastAPI Users, httpx OAuth dan PyJWT digunakan; PKCE, nonce/state browser binding, strict claims, bounded responses, secure cookie, token hashes, revoke-all dan CAS credential changes. TLS/origin/body/rate-limit boundaries sudah ada. | FastAPI Users maintenance mode, perlu pemantauan security. Password public sengaja OFF. Fresh Google consent/browser session tidak diuji langsung dalam audit. |
| Workspace/replay | Admission, durable commands dan causal clipping mempunyai tes; source/provider tetap controller-side. | UI historical XAU dua tahun belum terbukti; live masih 16 synthetic demos. Latensi multi-user dan perjalanan browser nyata belum dibenchmark. |
| Account/session | Session hub, metadata cards, basic stats/journal, grouped positions dan mobile bottomsheet sudah ada. | Cross-session Strategies/Journal/Statistics disabled soon. Profile name/preferences/password UI/API, advanced stats dan data-backed card sparkline/progress belum lengkap. Jangan mengarang metrik UI. |

## Dashboard dan desain Claude

Review menggunakan `docs/design/RIKSORA_WORKFLOW.md`, `RIKSORA_PLAYFUL_UI_PLAN.md`, product design blueprint, draft Claude dan 12 patch lokal. Brand C ribbon/navy/ice/yellow, Google card, avatar/logout-all dan sejumlah workspace panels sudah diterapkan. Screenshot publik login1440×900 diperiksa. Perbandingan functional vs draft Claude hanya lima file berbeda, sehingga menerapkan semua patch lagi berisiko menimpa perubahan yang sudah masuk.

**Status: sebagian sesuai, kesamaan visual penuh belum dapat disahkan.** [Canvas sumber Claude](https://claude.ai/artifact/5AHxbsfoT3xdaxuMi4mJMb) meminta sign-in; tidak ada export lengkap yang ditemukan pada lokasi lokal relevan. Browser interaktif juga tidak tersedia. HTTP200/screenshot login tidak membuktikan perjalanan dashboard terautentikasi.

Gap berdasarkan daftar Claude terakhir: landing/signin, toolbar/rail dan floating replay Workspace10, segmented orders/risk chips, mobile replay overlay, per-session cards berbasis data, advanced Stats15, Journal14 rating/exit price, Plans, Strategies16, Members21 dan Onboarding23. Unit conversion dan metrik yang belum tersedia harus menunggu kontrak/API; jangan membuat angka contoh menjadi hasil finansial. Daftar lama perlu direkonsiliasi terhadap kandidat integrasi, bukan dianggap seluruhnya belum dikerjakan. Arahan patch0012 menyerahkan alignment tersisa ke Codex; blocker adalah akses bukti visual dan kesiapan data, bukan kepemilikan Claude.

## CRM dan pembayaran

**Reuse Odoo19 existing.** Addon LGPL-3 memakai crm/contacts/account/mail, database bisnis terpisah, exporter read-only repeatable-read dan column grants. Projection bukan entitlement/financial truth. JSON2 memakai batas payload, HTTPS, tanpa redirects/proxy environment dan identity/company binding. Ini sudah lebih cocok daripada menambah CRM kedua. Namun actual Odoo19 runtime, ACL multi-company, backup+filestore, dashboard/Ninja theme dan alur balasan support ke produk belum memperoleh acceptance nyata. Mock/native backend tests tidak membuktikan keseluruhan Odoo bekerja.

**Pertahankan adapter Midtrans sandbox existing.** Signature bukan authority tunggal: status GET divalidasi terhadap merchant/currency/amount/transaction, immutable order dan reconciliation terkunci. Checkout-start disimpan sebelum POST, tidak blind retry; timeout, body cap dan redirect guard sudah ada. Spot-check SDK resmi menunjukkan redirects diizinkan, tanpa timeout eksplisit dan parsing response tak dibatasi; menggantinya langsung dapat mengurangi guard. Gunakan kontrak/payload resmi sebagai referensi. Billing aktif `false`; produksi, refund/renewal, accounting/tax dan persetujuan provider belum selesai. Tidak mengaktifkan pembayaran.

## Referensi open-source dan keputusan reuse

Lisensi diperiksa pada upstream saat audit; dependency/transitive dan kewajiban distribusi tetap harus diperiksa sebelum copying/shipping. Lisensi software tidak memberikan hak market data.

| Upstream | Lisensi / pin diperiksa | Keputusan |
| --- | --- | --- |
| [FastAPI Users](https://github.com/fastapi-users/fastapi-users) | MIT; e9c57ff7 | KEEP existing; maintenance mode, pantau security; tidak perlu rewrite login sekarang. |
| [Keycloak](https://github.com/keycloak/keycloak) | Apache-2.0;7e07aeec | Tunda; referensi staff SSO/MFA bila diperlukan, menambah service/DB. |
| [shadcn/ui](https://github.com/shadcn-ui/ui) | MIT;ffd22577 | Pilih komponen aksesibel setelah konteks Claude jelas; jangan mengganti seluruh desain/Tailwind stack. |
| [TanStack Table](https://github.com/TanStack/table) | MIT;c14e0221 | Kandidat table/filter UI; exact money strings dan server authority harus dipertahankan. |
| [Odoo19](https://github.com/odoo/odoo/tree/19.0) | LGPL-3;faee5d86 | KEEP addon existing, uji runtime19; jangan otomatis pindah versi default upstream20. |
| [Frappe CRM](https://github.com/frappe/crm) | AGPL-3;85af16ce | Referensi UX pipeline; jangan jalankan CRM duplikat. Tinjau kewajiban network/source sebelum memakai kode. |
| [Midtrans Python](https://github.com/Midtrans/midtrans-python-client) | MIT;72883f5b | Referensi kontrak saja sampai guard parity terbukti; last upstream push2023, bukan alasan membuang adapter existing. |
| [Lago](https://github.com/getlago/lago) | AGPL-3;117b8219 | Tunda subscription/usage billing; bukan drop-in Midtrans dan menambah operasi. |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3;9e6628ca | Referensi catalog/clock/event traces saja; tidak mengganti kernel RIKSORA. |
| [LEAN](https://github.com/QuantConnect/Lean) | Apache-2.0;f3d841e6 | Referensi provider/regression architecture; C# engine bukan modul drop-in. |
| [Playwright](https://github.com/microsoft/playwright) | Apache-2.0;b4695e3e | Kandidat bernilai tinggi untuk browser workflow/visual regression berikutnya. Belum dipasang. |
| [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) | Apache-2.0;9d7aad18 | Opsional observability terukur; batasi PII/secrets/ticks dan jangan tambah collector sebelum perlu. |

Arrow/Parquet26, DuckDB2 dan Lightweight Charts5.2.1 telah direview pada checkpoint sebelumnya di handoff yang sama. Gunakan benchmark existing; jangan menambah chart engine/database service baru. PoC hanya110,000 tick terbatas dengan warm-cache tak terkontrol, bukan kapasitas dua tahun. Kenaikan RAM Arrow dan full materialization DuckDB sudah dilaporkan; hasil query cepat tidak menghapus biaya itu. Original source dan identity/ordering authority tidak diganti.

## VPS, storage dan data

Host native Ubuntu24.04,6 vCPU,15GiB RAM, tanpa swap; observasi disk sekitar197GiB total/146GiB available. Caddy, riksora-beta, PostgreSQL16, SSH, Tailscale, GDM dan GNOME remote aktif; automatic restarts service yang diperiksa nol. API127.0.0.1:8001 dan PG127.0.0.1:5432; public binds80/443/22,3389 semua interface. xrdp-sesman failed; firewall efektif belum terverifikasi tanpa akses tambahan. Ini temuan operasional untuk ditinjau, bukan izin mengubah jaringan.

Backup harian terakhir sukses24 Oktober00:00UTC, tetapi belum ada bukti restore produksi/offhost terkini. Total storage forecast dua tahun harus memasukkan raw+canonical+index+derived+backup+temporary conversion dan free-space reserve; free disk bukan kapasitas dataset tervalidasi. Object storage bukan alasan menunda perbaikan engine/security lokal, tetapi ekspansi instrumen tetap ditunda.

Repository juga membawa965 file market legacy dan3,486,461 candle M1 derived2016–2026. Inventaris hak mencakup asset turunan yang sudah publik di Git, bukan hanya tick baru. Blocking `/market` di Caddy tidak menyembunyikan file Git publik. Tidak ada data dihapus atau history ditulis ulang. Root license proyek tidak ditemukan pada baseline; owner perlu menentukan lisensi milik sendiri secara eksplisit. Notices chart existing dipertahankan.

## Bukti pengujian sesungguhnya

| Gate | Hasil / batas |
| --- | --- |
| Backend lengkap | **573 PASS,0 skip,433.014s** pada private socket-only SCRAM PostgreSQL melalui helper repository, sourceba63. Percobaan pertama trust-only cluster gagal satu tes karena fixture tidak punya password; diulang dengan helper SCRAM yang benar, tanpa mengubah tes. |
| Frontend regression | Semua registered suites PASS; termasuk seluruh3,486,461 M1/11 timeframes, golden vectors, Beta client/workspace. Linux memakai override terdokumentasi `BTL_RESEARCH_PYTHON`; default path Windows masih portability debt. |
| Lint/build/release | PASS; staging workspace/home build terpisah PASS103 modules. Main build warning mixed static/dynamic AlphaHome import tetap ada; original PNG1.23MB bisa dioptimalkan nanti. |
| Deploy filesystem/package/audit tests | **23 PASS** pada temporary/mocked filesystem; output upgrade/rollback bukan perubahan layanan live. Allowlist preview.css/home.html/homeEntry.jsx/workspaceEntry.jsx diperiksa dan benar, bukan packaging bug. |
| Native deploy integration | **1 PASS,2.633s**, private SCRAM cluster: runtime role/migrations/grants/auth/support. Cluster QA dihentikan; tidak memakai production DSN. |
| Dependency scan | npm2 high packages, production0; pip-audit38 pins/1 known vulnerability(certifi), actual installed version diperiksa. Tools audit di venv/tmp tersendiri. |
| Public smoke | root/login/app HTTP200; anonymous workspaces401; Google configured true, password false, billing false, demo true. Tidak ada real trade, Google consent atau checkout. |

Log privat berada di `/tmp/riksora-comprehensive-backend-scram.log`, `/tmp/riksora-comprehensive-native-deploy.log`, `/tmp/riksora-comprehensive-npm-audit.json`, `/tmp/riksora-comprehensive-python-audit.json`; screenshot `/tmp/riksora-login-audit.png`. Ini artefak lokal temporer, bukan janji arsip permanen. Tidak memasukkan raw tick, credential atau signed media URL ke Git.

## Urutan checkpoint yang disarankan

1. Patch dependency security di kandidat terpisah, uji penuh, review diff; tidak restart layanan. Ini rekomendasi checkpoint berikut, belum diimplementasikan oleh audit.
2. Rakit manifest dan kandidat integrasi dari branch yang benar, pastikan source/runtime/test baseline konsisten; jangan merge draft otomatis.
3. Tuntaskan calendar/precision/provenance XAU, investigasi Oktober dari original evidence, serta hak penggunaan. Jalankan bounded probe sebelum admission; tidak mass import.
4. Tetapkan definisi engine selesai berdasarkan kontrak: exact evidence/execution equivalence, causal boundaries, crash/replay/idempotency, analysis caps dan honest unavailable states, backup/restore, RAM/storage/SLO beban sasaran. Jangan menaikkan cap atau mengganti kernel tanpa checkpoint sah.
5. E2E autentikasi→session→workspace→replay→stats dan error recovery; setelah akses canvas tersedia, rekonsiliasi desain Claude memakai data nyata. Playwright layak dipakai.
6. Setelah engine dan workflow diterima, uji Odoo nyata; billing tetap OFF sampai semua gate komersial/provider dan rollout disetujui. Instrumen tambahan menunggu object storage dan admission masing-masing.

Tidak ada perubahan engine finansial, raw data, service, pembayaran atau infrastructure dalam audit ini. GO hanya untuk engineering terisolasi yang tidak terblokir; public historical release dan klaim dua tahun lengkap tetap NO-GO.
