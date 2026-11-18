# RIKSORA MI benchmark readiness and unit-cost worksheet

Status: **preparation only**. No benchmark was run during this checkpoint. VPS2 is unavailable and excluded.

## Host and safety decision

The checkout is on Linux, not the owner's Windows machine. The Windows SSH key and trusted host-key entry are absent here. The project identifies 172.255.209.213 as the VPS1 address, but this Linux session cannot verify its host identity. Do not connect until tools/ops/inspect-vps1-readonly.ps1 succeeds from the Windows account with the existing key and trusted known_hosts entry.

The local host snapshot before deciding whether to benchmark showed 6 CPUs, about 13.8 GiB MemAvailable, no swap, and 148 GiB free on the workspace filesystem. Those free resources do not establish isolation. Local API and worker processes, PostgreSQL clusters, Caddy, and Claude/Codex processes were active. No isolated QA machine was identified. The 10k–1m engine benchmark and concurrency tests were therefore not started.

## Existing measurements and their scope

The historical report RIKSORA-VPS1-MAXIMUM-ECONOMIC-CAPACITY.md describes a legacy single-instrument synthetic product workload on VPS1, using 4 workers, 6 direct-operation slots, DB budget 24, API admission 16 plus 32 waiting slots, connection pooling, and client request reduction. It records 60 traders sustained for 15 minutes with 0.07% rejection and 75 with 0.90% rejection. At 75, CPU averaged 2.16 of the 5 SUT cores, SUT peak memory was 1.83 GB, PostgreSQL had at most 39 connections, database growth was 185 MB and WAL growth 359 MB. The generator shared the host. These are legacy measurements and do not establish MI capacity.

The existing MI durable smoke benchmark is much smaller. It runs one serial Session, 24 timestamp groups, and the same single EURUSD completed trade while adding idle instruments. Medians recorded in the 2026-11-18 checkpoint were:

| Instruments | Ticks | Worker CPU | Worker wall | Peak RSS | Final checkpoint | DB size delta |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 24 | 0.146 s | 0.263 s | 180.7 MiB | 3,639 B | 120 KiB |
| 4 | 96 | 0.319 s | 0.440 s | 180.7 MiB | 9,514 B | 120 KiB |
| 8 | 192 | 0.578 s | 0.700 s | 180.7 MiB | 18,140 B | 136 KiB |
| 16 | 384 | 1.122 s | 1.249 s | 180.7 MiB | 35,938 B | 176 KiB |

The test checks exact state and event parity against its chronological reference. It is a small smoke workload, not a capacity benchmark. It cannot be fairly compared with the historical legacy trader test.

## Unit economics

The historical VPS rental assumption is Rp270,000/month. Applying it only to the historical legacy measurements gives Rp4,500 per 60 sustained trader slots/month or Rp3,600 per 75 slots/month, before storage, backups, bandwidth, payment fees, support, and idle reserve. These figures do not describe MI or an approved production configuration.

MI cost per trader and MI sustainable capacity remain **unknown**. For a measured MI capacity N and assumed active-user share u, a basic rental-only estimate is Rp270,000 / (N / u) per registered customer-month. The variable N must come from a representative MI sustained run. Do not populate it with legacy capacity or the 24-timestamp smoke benchmark.

## Reproduction and next safe test environment

From the Windows machine, run the read-only host inventory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\\tools\\ops\\inspect-vps1-readonly.ps1
```

The script requires the local key and an already trusted host-key entry. It sets StrictHostKeyChecking=yes, limits output to host/resource/service/process and allowlisted runtime settings, and performs read-only remote commands.

For benchmark work, use a verified disposable QA host or an isolated local runner with exclusive resource limits and no active product services. Start with the existing native MI harness and expand it to fixed identical financial-active timestamp streams at 10k, 100k, 250k, 500k, and 1m events. Compare legacy and MI at 1/4/8/16 instruments, reporting reducer-only and durable worker paths separately. Require independent exact state/event/receipt parity at every tier. Do not extrapolate engine-only rates into trader capacity.
