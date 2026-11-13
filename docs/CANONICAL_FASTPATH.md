# Canonical walk fast path (BTL-CJSON-1 `_normalize`)

`contracts/canonical._normalize` is the validator/normalizer under every `canonical_bytes`, `content_hash` and
`canonical_v2_bytes` call. A profile of timeline advance and resume on synthetic data showed it as the largest single
cost (about 40% of profiled time). It is a pure function, so it can be made faster without changing any byte.

## Change
`_normalize` now delegates to `_walk`: same checks in the same order, same `ContractError(code, field)`, same
node-budget accounting (decremented once per node before other checks, so a failure leaves the shared budget exactly as
before). Fewer function calls: no `require()` on the happy path, no generator-based `all`, leaf children handled inline.
Output bytes, errors and budget are unchanged; no wire format, hash or contract changes.

## Proof of equivalence
`backend/tests/test_canonical_fastpath.py` keeps the original implementation verbatim as a reference and compares it with
the new one on 6,000 random trees (valid and invalid: floats, bytes, str/int/list subclasses, lone surrogates, oversized
strings and containers, integers around 2^53, deep nesting, ordered mappings, tiny budgets). Output, exception code/field
and remaining budget must all match. Also checks depth/size limits and a realistic tick chunk.

## Measured (synthetic 3,000 groups, session start set properly, same machine, 2 alternating runs each)
| | reference | fast path |
|---|---|---|
| advance | 4.0 s / 1.8 s | 1.4 s / 1.5 s |
| cold resume | 2.2 s / 2.2 s | 1.8 s / 1.6 s |

Checkpoints are identical. The first reference run was inflated by a cold cache; the steadier comparison is about
20-25% less time. This is a small-sample, noisy desktop measurement, not a benchmark claim.

## Measurement pitfall found while doing this
`IndexedTickTimeline` defaults `session_start_ns` to `"0"`. Evidence is queried in 1-day windows from the previous
cursor, so a session started at epoch 0 and advanced to 2023 runs about 19,700 empty-window evidence queries
(85% of advance time in my profile). Earlier numbers of "about 10 s to resume 2,048 groups" were inflated by this; with a
real session start the same resume is about 1-2 s per 3,000 groups. Real product sessions set their start, so this is a
benchmark trap, not a product regression. Any benchmark should pass the true session start.

## Not done
Further gains need fewer repeated canonicalizations of the same data (tick `_validate` re-walks events); that touches
validation boundaries and needs owner review.
