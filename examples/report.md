# AdPilot media-buyer report

_Mode: offline deterministic planner (no LLM). Data: 392 rows, 2025-03-03 to 2025-03-30. Gross margin 35%._

> AdPilot only **recommends**. It has no access to live ad accounts and never changes budgets, pauses ads or publishes anything. You apply (or ignore) every action yourself.

## Executive summary

- Blended ROAS is **3.11** on spend of 169,891, above the break-even ROAS of **2.86** (1 / 35% margin).
- **7 ads to kill**, **5 to scale**, 2 borderline, 0 with too little spend to judge (guard: 300 spend).
- **3 fatigued** and 0 at-risk creatives.
- Proposed budget move: 89.56 per day (max 20% per ad set per day).

## Account snapshot

| Platform | Spend | ROAS | CPA | CTR | CPM | CVR |
|---|---|---|---|---|---|---|
| google | 50,196 | 4.24 | 16.23 | 2.38% | 14.73 | 3.80% |
| meta | 74,792 | 3.06 | 20.32 | 1.60% | 10.20 | 3.13% |
| tiktok | 44,904 | 1.93 | 30.04 | 1.23% | 5.53 | 1.50% |
| **all** | 169,891 | 3.11 | 20.55 | 1.58% | 9.01 | 2.77% |

## What to kill

ROAS below 2.29 (80% of break-even) with enough spend to trust it.

| Ad | Spend | ROAS | CPA | CTR | CVR |
|---|---|---|---|---|---|
| Static_Promo (tiktok) | 7,023 | 0.23 | 250.83 | 0.60% | 0.40% |
| Creator_Duet_Trend (tiktok) | 10,180 | 0.52 | 109.46 | 0.90% | 0.52% |
| Static_Discount_Banner (meta) | 12,962 | 0.70 | 87.00 | 0.80% | 1.64% |
| RSA_Generic_2 (google) | 15,725 | 0.72 | 92.50 | 2.15% | 0.99% |
| RSA_Generic_1 (google) | 16,020 | 0.86 | 75.92 | 2.18% | 1.14% |
| Hook_ASMR_Unboxing (tiktok) | 14,581 | 1.51 | 38.27 | 1.07% | 1.35% |
| Carousel_Bestsellers (meta) | 10,705 | 1.71 | 35.68 | 1.21% | 2.47% |

## What to scale

ROAS at least 3.43 (120% of break-even).

| Ad | Spend | ROAS | CPA | CTR | CVR |
|---|---|---|---|---|---|
| RSA_Brand_1 (google) | 5,709 | 26.47 | 2.65 | 9.53% | 8.78% |
| DPA_Catalog (meta) | 7,101 | 6.75 | 9.07 | 2.77% | 5.53% |
| Hook_Problem_Solution (tiktok) | 13,120 | 4.39 | 13.21 | 2.00% | 2.13% |
| UGC_Testimonial_V1 (meta) | 15,661 | 4.17 | 15.06 | 1.88% | 3.21% |
| UGC_Testimonial_V2 (meta) | 15,290 | 3.75 | 16.75 | 1.85% | 2.98% |

Borderline (between 80% and 120% of break-even; let them run or iterate the creative): Feed_Main (google) (2.85), Founder_Story_Video (meta) (2.35).

## Fatigued creatives

Rolling 7-day CTR versus its own peak, plus latest frequency. 'Fatigued' = decay >= 25% and frequency >= 3.0; 'at risk' = one of the two.

| Ad | Status | CTR decay from peak | Latest freq. | Rolling CTR now |
|---|---|---|---|---|
| Hook_ASMR_Unboxing (tiktok) | fatigued | 73.6% | 4.65 | 0.45% |
| Founder_Story_Video (meta) | fatigued | 64.0% | 4.60 | 0.75% |
| DPA_Catalog (meta) | fatigued | 40.9% | 4.57 | 1.92% |

Action: refresh the creative (new hook and first 3 seconds, same offer) rather than raising budget on it.

## Budget moves (proposal)

Cuts and increases are capped at 20% of each ad set's recent daily budget (last 7 days). Total daily budget is unchanged.

| Ad set | Action | ROAS | Now / day | Change / day | Proposed / day |
|---|---|---|---|---|---|
| Broad (tiktok) | decrease | 0.40 | 622.79 | -18.38 (-3.0%) | 604.41 |
| Generic Broad (google) | decrease | 0.79 | 1,124.16 | -33.18 (-3.0%) | 1,090.98 |
| LAL 1% Buyers (meta) | decrease | 2.06 | 834.43 | -24.63 (-3.0%) | 809.80 |
| PMax Feed (google) | decrease | 2.85 | 453.17 | -13.37 (-3.0%) | 439.80 |
| Visitors 30d (meta) | increase | 6.75 | 250.81 | +50.16 (+20.0%) | 300.97 |
| Brand Exact (google) | increase | 26.47 | 196.99 | +39.40 (+20.0%) | 236.38 |

_Estimate assumes historical ROAS holds at the new spend level, which it often does not (diminishing returns). Apply gradually and re-check. AdPilot does not change budgets._ Estimated daily revenue delta at historical ROAS: 1,258.83.

## A/B test verdicts (CTR, two-proportion z-test)

| A | B | CTR A | CTR B | Lift | p-value | Verdict |
|---|---|---|---|---|---|---|
| RSA_Generic_1 | RSA_Generic_2 | 2.18% | 2.15% | -1.2% | 0.2330 | No significant difference at alpha=0.05 (p=0.2330); keep testing or call it a tie |
| UGC_Testimonial_V1 | UGC_Testimonial_V2 | 1.88% | 1.85% | -1.6% | 0.0360 | B is worse than A (p=0.0360) |
| Hook_ASMR_Unboxing | Hook_Problem_Solution | 1.07% | 2.00% | 87.9% | 0.0000 | B is better than A (p=0.0000) |

## New hooks to test

**For `Hook_ASMR_Unboxing`** (template-generated, angle: asmr):
- Wait for the unboxing... a skincare serum sounds as good as it looks.
- Opening a skincare serum so you don't have to guess what's inside.
- No talking, just a skincare serum. Watch until the end.

**For `Founder_Story_Video`** (template-generated, angle: founder):
- I started a skincare serum because every product I tried failed me.
- Why I quit my job to build a skincare serum (the honest version).
- Three mistakes I made building a skincare serum so you don't repeat them.

## Caveats

- Attribution is whatever the platform exported (view-through, windows and double counting differ by platform).
- ROAS is revenue / spend; margin is applied only through the break-even threshold.
- Statistical tests treat impressions as independent; real delivery is not, so treat p-values as a guide.

## Appendix: tool calls

| # | Tool | Input | OK |
|---|---|---|---|
| 1 | compute_kpis | `{}` | yes |
| 2 | compute_kpis | `{"group_by": ["platform"]}` | yes |
| 3 | breakeven_roas | `{}` | yes |
| 4 | find_winners_losers | `{}` | yes |
| 5 | detect_creative_fatigue | `{}` | yes |
| 6 | propose_budget_reallocation | `{}` | yes |
| 7 | ab_test | `{"ad_a": "RSA_Generic_1", "ad_b": "RSA_Generic_2", "metric": "ctr"}` | yes |
| 8 | ab_test | `{"ad_a": "UGC_Testimonial_V1", "ad_b": "UGC_Testimonial_V2", "metric": "ctr"}` | yes |
| 9 | ab_test | `{"ad_a": "Hook_ASMR_Unboxing", "ad_b": "Hook_Problem_Solution", "metric": "ctr"}` | yes |
| 10 | generate_ad_hooks | `{"product": "a skincare serum", "angle": "asmr", "n": 3}` | yes |
| 11 | generate_ad_hooks | `{"product": "a skincare serum", "angle": "founder", "n": 3}` | yes |
