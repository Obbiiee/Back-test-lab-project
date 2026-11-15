# RIKSORA unit economics (generated; IDR)

## 1. Fixed monthly cost (data licence EXCLUDED by owner instruction; own labour and marketing excluded)
| Item | Rp / month |
|---|---:|
| VPS 6 vCPU / 16 GB (GIVEN) | 270,000 |
| Domain (ASSUMPTION) | 16,667 |
| Legal documents amortised (ASSUMPTION) | 416,667 |
| Bookkeeping (ASSUMPTION) | 200,000 |
| SMTP / R2 / monitoring / Google OAuth (PUBLIC free tiers) | 0 |
| Subtotal | 903,333 |
| Contingency 10% (ASSUMPTION) | 90,333 |
| **Operational fixed total** | **993,667** |
| Lean floor (VPS + domain only) | 286,667 |
| Optional second node for HA | +270,000 |

## 2. Compute capacity of one VPS
Budget 5 vCPU x 2,592,000 s x average utilisation 20% = **2,592,000 usable core-seconds / month**. Replay speed MEASURED: 2,372 (optimistic, isolated) to 809 (conservative, full journey) ticks per core-second.

Core-seconds per trader-month (persona ticks per month are ASSUMPTIONS; read/export overhead is an ASSUMPTION, not measured):
| Persona | Ticks / month | Share | Core-s optimistic | Core-s conservative |
|---|---:|---:|---:|---:|
| light | 500,000 | 75% | 241 | 648 |
| medium | 3,000,000 | 20% | 1,385 | 3,829 |
| heavy | 15,000,000 | 4% | 6,723 | 18,945 |
| abusive | 100,000,000 | 1% | 42,952 | 124,434 |
| **Blended paying trader** | | | **1,156** | **3,254** |
| Blended with abusive capped at 30,000,000 ticks | | | 861 | 2,389 |
| Free user (ASSUMPTION 300,000 ticks) | | | 146 | 391 |

Paying subscribers one VPS can carry by CPU (ESTIMATED, assumes traffic fits the measured concurrency; measured only up to 8 simultaneous heavy Sessions):
| Case | Optimistic | Conservative |
|---|---:|---:|
| Paying only, abusive uncapped | 2,242 | 797 |
| Paying only, abusive capped | 3,011 | 1,085 |
| With free users (3% conversion = 32 free per payer), abusive capped | 463 | 172 |

## 3. Storage (hot tier = this SSD; cold tier = R2 for user data only, per owner decision 2026-11-14)
| Persona | Ticks / month | DB growth MB / month |
|---|---:|---:|
| light | 500,000 | 25 |
| medium | 3,000,000 | 149 |
| heavy | 15,000,000 | 744 |
| abusive | 100,000,000 | 4,959 |

Paying trader (abusive capped): 93 MB/month, 1.12 GB held at 12-month retention. Free user: 15 MB/month, 0.04 GB held at 3-month retention. Per paying subscriber including its 32 free users: **2.56 GB**.
Hot-tier limit: 158 GB free on this SSD / 2.56 GB = **about 62 paying subscribers** (with their free users) before the SSD is full. Retention, cap and archiving are therefore product decisions; checkpoint bytes per tick are MEASURED, everything else ASSUMPTION. Immutable financial evidence must not be deleted, so growth is handled by archiving to R2, not by pruning.
Archive cost if all of it sat on R2: 2.56 GB x $0.015/GB-month x 16,500 = **Rp 633 per paying subscriber per month** (PUBLIC price; first 10 GB free ignored).

## 4. Revenue per subscriber after payment fee and tax
Payment mix (ASSUMPTION): QRIS 40%, Virtual account 30%, E-wallet 20%, Card 10%. Fee includes 11% VAT on the fee; income tax 0.5% of gross (ASSUMPTION, confirm with an accountant); non-PKP (no output VAT) assumed.
| Price Rp / month | Payment fee | Fee % | Income tax | R2 storage | **Net per subscriber** |
|---:|---:|---:|---:|---:|---:|
| 49,000 | 2,082 | 4.2% | 245 | 633 | **46,040** |
| 99,000 | 2,620 | 2.6% | 495 | 633 | **95,252** |
| 149,000 | 3,158 | 2.1% | 745 | 633 | **144,463** |
| 199,000 | 3,697 | 1.9% | 995 | 633 | **193,675** |
| 299,000 | 4,773 | 1.6% | 1,495 | 633 | **292,098** |

## 5. Break-even and profit (fixed total 993,667; one more VPS of 270,000 each time CPU capacity is exceeded)
Capacity used for stepping: conservative, abusive capped, with free users = 172 paying subscribers per VPS.

| Price | Break-even paying subs (one VPS) | Profit @ 50 | @ 100 | @ 250 | @ 500 | @ 1,000 |
|---:|---:|---:|---:|---:|---:|---:|
| 49,000 | 22 | 1,308,338 | 3,610,342 | 10,246,356 | 21,486,378 | 43,696,423 |
| 99,000 | 11 | 3,768,920 | 8,531,507 | 22,549,268 | 46,092,203 | 92,908,073 |
| 149,000 | 7 | 6,229,503 | 13,452,672 | 34,852,181 | 70,698,028 | 142,119,723 |
| 199,000 | 6 | 8,690,085 | 18,373,837 | 47,155,093 | 95,303,853 | 191,331,373 |
| 299,000 | 4 | 13,611,250 | 28,216,167 | 71,760,918 | 144,515,503 | 289,754,673 |

Compare, not a decision: TradingView (public list, verify) Essential $14.95, Plus $34.95, Premium $69.95 per month, i.e. about Rp 246,675, 576,675, 1,154,175 at the assumed rate.
