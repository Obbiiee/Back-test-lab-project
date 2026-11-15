"""RIKSORA unit-economics model (IDR). Every input is a labelled constant; change it and rerun:  python3 unit_economics.py > RIKSORA-UNIT-ECONOMICS-TABLES.md
MEASURED = from our benchmarks; GIVEN = stated by the owner; PUBLIC = public price page (verify); ASSUMPTION = placeholder the owner must replace.
Data-licence cost is EXCLUDED by owner instruction (2026-11-15): it is a legal/commercial risk, not a zero."""
import math

# ---------------- inputs ----------------
VPS_RP = 270_000                      # GIVEN: current VPS (6 vCPU / 16 GB) per month
USD_IDR = 16_500                      # ASSUMPTION exchange rate
DOMAIN_YEAR_RP = 200_000              # ASSUMPTION .com per year
LEGAL_ONE_TIME_RP, LEGAL_MONTHS = 5_000_000, 12   # ASSUMPTION lawyer for ToS/privacy/disclaimer, amortised
BOOKKEEPING_RP = 200_000              # ASSUMPTION per month
CONTINGENCY = 0.10                    # ASSUMPTION on fixed costs
HA_SECOND_NODE_RP = 270_000           # optional
SMTP_RP, R2_RP, MONITOR_RP = 0, 0, 0  # PUBLIC free tiers (R2 10 GB free; SES/Brevo free tier; UptimeRobot free) at this scale

BUDGET_VCPU = 5                       # GIVEN owner budget for the website stack
SECONDS_MONTH = 30 * 24 * 3600
UTIL = 0.20                           # ASSUMPTION average utilisation that keeps peaks safe (bursty traffic)
TICKS_PER_CORE_S = {"optimistic": 262_144 / 110.5, "conservative": 262_144 / 324.1}   # MEASURED (isolated replay / full 20-trader journey)
DB_BYTES_PER_TICK = 13_000_000 / 262_144          # MEASURED (+14.6 MB DB per 262,144-tick Session incl. checkpoints)
DISK_FREE_GB, DATA_GB, RETENTION_MONTHS = 165, 6.9, 12   # MEASURED disk / data; ASSUMPTION retention (paying)
FREE_RETENTION_MONTHS = 3                              # ASSUMPTION retention of free-user Sessions
R2_USD_GB_MONTH = 0.015                                # PUBLIC Cloudflare R2 Standard; first 10 GB free (ignored: conservative)

# persona: (ticks advanced per month, read/export overhead core-s per month [ASSUMPTION])
PERSONAS = {"light": (0.5e6, 30), "medium": (3e6, 120), "heavy": (15e6, 400), "abusive": (100e6, 800)}
MIX = {"light": .75, "medium": .20, "heavy": .04, "abusive": .01}      # ASSUMPTION
ABUSE_CAP_TICKS = 30e6                                                  # product cap proposal for abusive users
FREE_TICKS, FREE_OVERHEAD = 0.3e6, 20                                   # ASSUMPTION per free user per month
CONVERSION = 0.03                                                       # ASSUMPTION free -> paid

# payments (Midtrans): QRIS 0.7 % and card 2.9 % are official; VA/e-wallet/card-fixed are third-party figures (verify). Fees exclude 11 % VAT.
PAY_MIX = [("QRIS", .40, .007, 0), ("Virtual account", .30, 0, 4000), ("E-wallet", .20, .02, 0), ("Card", .10, .029, 2000)]
FEE_VAT = 0.11
INCOME_TAX = 0.005                                                      # ASSUMPTION UMKM final tax on gross; confirm with an accountant
PRICES = [49_000, 99_000, 149_000, 199_000, 299_000]                    # candidate prices per month (not decided)

def rp(x): return f"{x:,.0f}"

def fixed():
    rows = [("VPS 6 vCPU / 16 GB (GIVEN)", VPS_RP), ("Domain (ASSUMPTION)", DOMAIN_YEAR_RP / 12), ("Legal documents amortised (ASSUMPTION)", LEGAL_ONE_TIME_RP / LEGAL_MONTHS),
            ("Bookkeeping (ASSUMPTION)", BOOKKEEPING_RP), ("SMTP / R2 / monitoring / Google OAuth (PUBLIC free tiers)", SMTP_RP + R2_RP + MONITOR_RP)]
    sub = sum(v for _, v in rows); cont = sub * CONTINGENCY
    return rows, sub, cont, sub + cont

def blended(cap_abuse, mode):
    tpc = TICKS_PER_CORE_S[mode]; out = {}
    for k, (ticks, over) in PERSONAS.items():
        t = min(ticks, ABUSE_CAP_TICKS) if (k == "abusive" and cap_abuse) else ticks
        out[k] = t / tpc + over
    out["blend"] = sum(MIX[k] * out[k] for k in PERSONAS)
    out["free"] = FREE_TICKS / tpc + FREE_OVERHEAD
    return out

def fee(price):
    total = 0
    for _, share, pct, flat in PAY_MIX:
        total += share * (price * pct + flat)
    return total * (1 + FEE_VAT)

def main():
    rows, sub, cont, total = fixed()
    print("# RIKSORA unit economics (generated; IDR)\n")
    print("## 1. Fixed monthly cost (data licence EXCLUDED by owner instruction; own labour and marketing excluded)\n| Item | Rp / month |\n|---|---:|")
    for n, v in rows: print(f"| {n} | {rp(v)} |")
    print(f"| Subtotal | {rp(sub)} |\n| Contingency {CONTINGENCY:.0%} (ASSUMPTION) | {rp(cont)} |\n| **Operational fixed total** | **{rp(total)}** |")
    print(f"| Lean floor (VPS + domain only) | {rp(VPS_RP + DOMAIN_YEAR_RP / 12)} |\n| Optional second node for HA | +{rp(HA_SECOND_NODE_RP)} |\n")
    usable = BUDGET_VCPU * SECONDS_MONTH * UTIL
    print(f"## 2. Compute capacity of one VPS\nBudget {BUDGET_VCPU} vCPU x {SECONDS_MONTH:,} s x average utilisation {UTIL:.0%} = **{usable:,.0f} usable core-seconds / month**. Replay speed MEASURED: {TICKS_PER_CORE_S['optimistic']:,.0f} (optimistic, isolated) to {TICKS_PER_CORE_S['conservative']:,.0f} (conservative, full journey) ticks per core-second.\n")
    print("Core-seconds per trader-month (persona ticks per month are ASSUMPTIONS; read/export overhead is an ASSUMPTION, not measured):\n| Persona | Ticks / month | Share | Core-s optimistic | Core-s conservative |\n|---|---:|---:|---:|---:|")
    o, c = blended(False, "optimistic"), blended(False, "conservative")
    for k, (t, _) in PERSONAS.items(): print(f"| {k} | {t:,.0f} | {MIX[k]:.0%} | {o[k]:,.0f} | {c[k]:,.0f} |")
    print(f"| **Blended paying trader** | | | **{o['blend']:,.0f}** | **{c['blend']:,.0f}** |")
    oc, cc = blended(True, "optimistic"), blended(True, "conservative")
    print(f"| Blended with abusive capped at {ABUSE_CAP_TICKS:,.0f} ticks | | | {oc['blend']:,.0f} | {cc['blend']:,.0f} |")
    print(f"| Free user (ASSUMPTION {FREE_TICKS:,.0f} ticks) | | | {o['free']:,.0f} | {c['free']:,.0f} |\n")
    free_per_paid = 1 / CONVERSION - 1
    print("Paying subscribers one VPS can carry by CPU (ESTIMATED, assumes traffic fits the measured concurrency; measured only up to 8 simultaneous heavy Sessions):\n| Case | Optimistic | Conservative |\n|---|---:|---:|")
    cap = {}
    for label, cap_abuse, with_free in (("Paying only, abusive uncapped", False, False), ("Paying only, abusive capped", True, False), (f"With free users ({CONVERSION:.0%} conversion = {free_per_paid:.0f} free per payer), abusive capped", True, True)):
        vals = []
        for mode in ("optimistic", "conservative"):
            b = blended(cap_abuse, mode); per = b["blend"] + (free_per_paid * b["free"] if with_free else 0)
            vals.append(usable / per)
        cap[label] = vals; print(f"| {label} | {vals[0]:,.0f} | {vals[1]:,.0f} |")
    print()
    print("## 3. Storage (hot tier = this SSD; cold tier = R2 for user data only, per owner decision 2026-11-14)\n| Persona | Ticks / month | DB growth MB / month |\n|---|---:|---:|")
    for k, (t, _) in PERSONAS.items(): print(f"| {k} | {t:,.0f} | {t * DB_BYTES_PER_TICK / 1e6:,.0f} |")
    paid_mb = sum(MIX[k] * (min(PERSONAS[k][0], ABUSE_CAP_TICKS) if k == 'abusive' else PERSONAS[k][0]) for k in PERSONAS) * DB_BYTES_PER_TICK / 1e6
    free_mb = FREE_TICKS * DB_BYTES_PER_TICK / 1e6
    paid_gb, free_gb = paid_mb * RETENTION_MONTHS / 1000, free_mb * FREE_RETENTION_MONTHS / 1000
    per_payer_gb = paid_gb + free_per_paid * free_gb
    room = DISK_FREE_GB - DATA_GB
    print(f"\nPaying trader (abusive capped): {paid_mb:,.0f} MB/month, {paid_gb:,.2f} GB held at {RETENTION_MONTHS}-month retention. Free user: {free_mb:,.0f} MB/month, {free_gb:,.2f} GB held at {FREE_RETENTION_MONTHS}-month retention. Per paying subscriber including its {free_per_paid:.0f} free users: **{per_payer_gb:,.2f} GB**.")
    print(f"Hot-tier limit: {room:,.0f} GB free on this SSD / {per_payer_gb:,.2f} GB = **about {room / per_payer_gb:,.0f} paying subscribers** (with their free users) before the SSD is full. Retention, cap and archiving are therefore product decisions; checkpoint bytes per tick are MEASURED, everything else ASSUMPTION. Immutable financial evidence must not be deleted, so growth is handled by archiving to R2, not by pruning.")
    store_cost = per_payer_gb * R2_USD_GB_MONTH * USD_IDR
    print(f"Archive cost if all of it sat on R2: {per_payer_gb:,.2f} GB x ${R2_USD_GB_MONTH}/GB-month x {USD_IDR:,} = **Rp {store_cost:,.0f} per paying subscriber per month** (PUBLIC price; first 10 GB free ignored).\n")
    print("## 4. Revenue per subscriber after payment fee and tax\nPayment mix (ASSUMPTION): " + ", ".join(f"{n} {s:.0%}" for n, s, _, _ in PAY_MIX) + f". Fee includes {FEE_VAT:.0%} VAT on the fee; income tax {INCOME_TAX:.1%} of gross (ASSUMPTION, confirm with an accountant); non-PKP (no output VAT) assumed.\n| Price Rp / month | Payment fee | Fee % | Income tax | R2 storage | **Net per subscriber** |\n|---:|---:|---:|---:|---:|---:|")
    net = {}
    for p in PRICES:
        f = fee(p); t = p * INCOME_TAX; n = p - f - t - store_cost; net[p] = n; print(f"| {rp(p)} | {rp(f)} | {f / p:.1%} | {rp(t)} | {rp(store_cost)} | **{rp(n)}** |")
    print()
    print(f"## 5. Break-even and profit (fixed total {rp(total)}; one more VPS of {rp(VPS_RP)} each time CPU capacity is exceeded)\nCapacity used for stepping: conservative, abusive capped, with free users = {cap[list(cap)[2]][1]:,.0f} paying subscribers per VPS.\n")
    print("| Price | Break-even paying subs (one VPS) | Profit @ 50 | @ 100 | @ 250 | @ 500 | @ 1,000 |\n|---:|---:|---:|---:|---:|---:|---:|")
    per_vps = cap[list(cap)[2]][1]
    for p in PRICES:
        be = math.ceil(total / net[p]); cells = []
        for s in (50, 100, 250, 500, 1000):
            vps = max(1, math.ceil(s / per_vps)); cost = total + (vps - 1) * VPS_RP
            cells.append(rp(s * net[p] - cost))
        print(f"| {rp(p)} | {be} | " + " | ".join(cells) + " |")
    print("\nCompare, not a decision: TradingView (public list, verify) Essential $14.95, Plus $34.95, Premium $69.95 per month, i.e. about Rp " + rp(14.95 * USD_IDR) + ", " + rp(34.95 * USD_IDR) + ", " + rp(69.95 * USD_IDR) + " at the assumed rate.")
if __name__ == "__main__":
    main()
