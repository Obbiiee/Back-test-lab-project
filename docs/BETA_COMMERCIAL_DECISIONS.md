# Beta commercial decisions worksheet

Draft for owner decisions; not published terms, a live price list or authorization to charge. Operational readiness is still owned by AI_CONTEXT/04_CURRENT_PHASE, and architecture by PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT. No billing/entitlement code is changed by this worksheet.

## Owner decision recorded

On2026-10-20 the owner selected Free plus Pro monthly and Pro annual, then specified IDR139000 monthly and IDR139000 x12 = IDR1668000 annual. These are approved draft base prices, not activated checkout settings. Period semantics, renewal/stacking, tax presentation and refund eligibility remain undecided. Existing merchant, company/chart/tax and host prerequisites remain open.

| Item | Free | Pro monthly | Pro annual |
| --- | --- | --- | --- |
| Draft product position | Practice trading | Paid access, monthly offer | Paid access, annual offer |
| Owner-selected draft base price in IDR | No charge |139000 |1668000 (139000 x12; no annual discount yet) |
| Trading allowed | Yes | Yes, subject to accepted production scope | Same accepted Pro scope unless owner chooses otherwise |
| Existing local sandbox saved-session cap |5 nontrashed v2 Sessions |128 under current Pro policy |128 under current Pro policy |
| Existing local activation rule |1 new monthly-window activation/day, reset00:00UTC; previously activated Sessions remain tradable | Free daily activation restriction lifted in sandbox | Same current Pro sandbox rule |
| Data currently demonstrated | Short authored16-symbol synthetic fixtures | Same authored QA source | Same authored QA source |
| Production data/history promise | Pending licensed data/coverage acceptance | Pending | Pending |
| Duration | No paid expiry |30days versus calendar month: undecided |365days versus calendar year: undecided |
| Renewal/overlap | Not applicable | Manual versus automatic renewal; overlap/extension rule pending | Same pending decision |
| Refund policy | Not applicable | Owner decision pending | Owner decision pending |

Sandbox values are current implementation evidence, not guaranteed commercial quotas or historical coverage. A new real one-month trading dataset and two-year OHLC context are deferred until VPS/data acceptance. Do not market synthetic fixtures as historical data, advertise unlimited replay/capacity or promise a production uptime/recovery level from local tests.

## Decisions needed before publishing offers

- Tax-inclusive/exclusive display and any future promotional discount; the owner-selected annual base price currently has no discount. No campaign amount, eligibility or dates are approved.
- Exact term definition and time boundaries, renewal behavior, early renewal/stacking, upgrade/downgrade, late payment and expiration. Existing paid orders have server-pinned fixed durations and exclusive expiry; duplicate success never renews an order. Independent paid orders may overlap; they are not automatically stacked.
- Refund eligibility/window/partial treatment, support process and approved customer wording. Existing conservative reversal access behavior is a technical policy, not a chosen commercial refund promise.
- Final Free/Pro limits after actual host/data/capacity acceptance, cohort size, support availability and escalation owner.
- Company identity, invoice/tax setup, accepted merchant channels, actual provider fee/payout reporting and bank reconciliation ownership.

## Safe sequence

Owner approves the above commercial decisions -> record them in the existing authority -> implement a bounded versioned offer/renewal change with regression tests -> validate actual merchant/accounting/host prerequisites -> approve the final customer-facing offer. Current sandbox QA prices/durations, Odoo fields and this draft must not silently become production settings.

## Future discounts and Midtrans

Midtrans Snap Promo Management supports merchant-configured campaigns (fixed/percentage discount, conditions, budget and voucher codes) through its dashboard. A discount is not automatic or necessarily funded by Midtrans. Product-wide offer pricing can instead be computed by the merchant backend before creating the Snap transaction. Use one explicit pricing authority per offer, preserve the base price/discount/final amount and campaign identity for reconciliation, and validate actual provider status/amount semantics before enabling a campaign. Do not relax the existing exact payment-verification contract to accept an unexpected discounted amount. Neither path is enabled by this worksheet.

Official references checked2026-10-20: [Promo Management](https://docs.midtrans.com/docs/promo-management), [Snap integration guide](https://docs.midtrans.com/docs/snap-snap-integration-guide).
