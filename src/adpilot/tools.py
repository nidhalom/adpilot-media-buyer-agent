"""Pure-Python analysis tools used by the agent.

Every function is deterministic and side-effect free (no network, no ad-account access).
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

AD_KEYS = ["platform", "campaign", "adset", "ad"]
ADSET_KEYS = ["platform", "campaign", "adset"]


def _div(a, b):
    return float(a) / float(b) if b else None


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


# --------------------------------------------------------------------------- KPIs
def kpis_from_totals(spend, impressions, clicks, purchases, revenue) -> dict:
    return {
        "spend": _r(spend, 2), "impressions": int(impressions), "clicks": int(clicks),
        "purchases": int(purchases), "revenue": _r(revenue, 2),
        "ctr": _r(_div(clicks, impressions), 5),
        "cpc": _r(_div(spend, clicks)),
        "cpm": _r(_div(spend, impressions) * 1000 if impressions else None),
        "cpa": _r(_div(spend, purchases)),
        "roas": _r(_div(revenue, spend)),
        "cvr": _r(_div(purchases, clicks), 5),
    }


def compute_kpis(df: pd.DataFrame, group_by: list[str] | None = None) -> list[dict]:
    """CTR, CPC, CPM, CPA, ROAS, CVR for the whole frame or per group.

    Ratios are computed from summed totals (never an average of daily ratios).
    Division by zero yields None.
    """
    cols = ["spend", "impressions", "clicks", "purchases", "revenue"]
    if not group_by:
        t = df[cols].sum()
        return [{"group": "all", **kpis_from_totals(*t[cols])}]
    for g in group_by:
        if g not in df.columns:
            raise ValueError(f"Unknown group_by column '{g}'")
    agg = df.groupby(group_by, dropna=False)[cols].sum().reset_index()
    out = []
    for _, r in agg.iterrows():
        label = " | ".join(str(r[g]) for g in group_by)
        out.append({"group": label, **{g: r[g] for g in group_by}, **kpis_from_totals(*[r[c] for c in cols])})
    return out


def breakeven_roas(margin: float) -> float:
    """ROAS at which gross-margin profit is zero: 1 / margin (margin is a fraction, e.g. 0.35)."""
    if not (0 < margin <= 1):
        raise ValueError("margin must be a fraction in (0, 1], e.g. 0.35 for 35%")
    return round(1.0 / margin, 4)


# ------------------------------------------------------------------------ fatigue
def detect_creative_fatigue(
    df: pd.DataFrame,
    window: int = 7,
    freq_threshold: float = 3.0,
    decay_threshold: float = 0.25,
    min_impressions: int = 5000,
) -> list[dict]:
    """Flag ads whose rolling CTR has decayed from its own peak while frequency is high.

    Per ad: daily impressions/clicks -> rolling `window`-day CTR (sum clicks / sum impressions).
    decay = 1 - latest_rolling_ctr / peak_rolling_ctr. The peak must occur before the latest window.
    status: 'fatigued' when decay >= decay_threshold AND latest frequency >= freq_threshold;
            'at_risk'  when only one of the two holds (or frequency is unavailable and decay holds);
            'healthy'  otherwise. Ads with fewer than `window`+3 days or too few impressions are skipped.
    """
    results = []
    for keys, g in df.groupby(AD_KEYS):
        daily = g.groupby("date").agg(
            impressions=("impressions", "sum"), clicks=("clicks", "sum"), freq=("frequency", "mean")
        ).sort_index()
        if len(daily) < window + 3 or daily.impressions.sum() < min_impressions:
            continue
        roll_i = daily.impressions.rolling(window).sum()
        roll_c = daily.clicks.rolling(window).sum()
        roll_ctr = (roll_c / roll_i).dropna()
        latest = float(roll_ctr.iloc[-1])
        prior = roll_ctr.iloc[: -1]
        peak = float(prior.max()) if len(prior) else latest
        peak = max(peak, latest)
        decay = 1 - latest / peak if peak > 0 else 0.0
        daily_ctr = (daily.clicks / daily.impressions).replace([np.inf], np.nan)
        slope = float(np.polyfit(np.arange(len(daily_ctr)), daily_ctr.fillna(0).values, 1)[0])
        rel_slope = slope / float(daily_ctr.mean()) if daily_ctr.mean() else 0.0
        freq_vals = daily.freq.dropna()
        latest_freq = float(freq_vals.iloc[-1]) if len(freq_vals) else None
        decayed = decay >= decay_threshold
        freq_high = latest_freq is not None and latest_freq >= freq_threshold
        if decayed and freq_high:
            status = "fatigued"
        elif decayed or freq_high:
            status = "at_risk"
        else:
            status = "healthy"
        results.append({
            **dict(zip(AD_KEYS, keys)),
            "status": status,
            "ctr_peak_rolling": _r(peak, 5), "ctr_latest_rolling": _r(latest, 5),
            "ctr_decay_pct": _r(decay * 100, 1),
            "ctr_trend_pct_per_day": _r(rel_slope * 100, 2),
            "latest_frequency": _r(latest_freq, 2),
            "series": [{"date": d.strftime("%Y-%m-%d"), "ctr": _r(c, 5)} for d, c in roll_ctr.items()],
        })
    order = {"fatigued": 0, "at_risk": 1, "healthy": 2}
    results.sort(key=lambda r: (order[r["status"]], -(r["ctr_decay_pct"] or 0)))
    return results


# ------------------------------------------------------------- winners and losers
def find_winners_losers(
    df: pd.DataFrame,
    breakeven: float,
    min_spend: float = 300.0,
    winner_mult: float = 1.2,
    loser_mult: float = 0.8,
    level: str = "ad",
) -> dict:
    """Classify ads (or adsets) by ROAS versus break-even, with a minimum-spend guard.

    Entities with spend < min_spend are 'insufficient_data' - never called winners or losers.
    winner: ROAS >= breakeven * winner_mult; loser: ROAS < breakeven * loser_mult;
    otherwise 'borderline'.
    """
    keys = AD_KEYS if level == "ad" else ADSET_KEYS
    agg = df.groupby(keys)[["spend", "impressions", "clicks", "purchases", "revenue"]].sum().reset_index()
    buckets = {"winners": [], "losers": [], "borderline": [], "insufficient_data": []}
    for _, r in agg.iterrows():
        k = kpis_from_totals(r.spend, r.impressions, r.clicks, r.purchases, r.revenue)
        row = {**{c: r[c] for c in keys}, **k}
        roas = k["roas"] or 0.0
        if r.spend < min_spend:
            buckets["insufficient_data"].append(row)
        elif roas >= breakeven * winner_mult:
            buckets["winners"].append(row)
        elif roas < breakeven * loser_mult:
            buckets["losers"].append(row)
        else:
            buckets["borderline"].append(row)
    buckets["winners"].sort(key=lambda x: -(x["roas"] or 0))
    buckets["losers"].sort(key=lambda x: (x["roas"] or 0))
    return {"breakeven_roas": breakeven, "min_spend": min_spend, "level": level, **buckets}


# ------------------------------------------------------------ budget reallocation
def propose_budget_reallocation(
    df: pd.DataFrame,
    breakeven: float,
    max_shift_pct: float = 0.20,
    lookback_days: int = 7,
    min_spend: float = 300.0,
    winner_mult: float = 1.2,
) -> dict:
    """Propose (never apply) a daily budget shift between ad sets.

    - Daily budget = mean daily spend over the last `lookback_days` days.
    - Below-break-even ad sets (full-period ROAS < breakeven, spend >= min_spend) are cut by
      at most `max_shift_pct` of their daily budget.
    - The freed pool goes to ad sets with ROAS >= breakeven * winner_mult, proportional to their
      ROAS surplus, each raised by at most `max_shift_pct` of its own daily budget.
    - Total proposed daily budget never exceeds the current total (unspent pool stays unallocated).
    """
    if not (0 < max_shift_pct <= 1):
        raise ValueError("max_shift_pct must be in (0, 1]")
    last = df["date"].max()
    recent = df[df["date"] > last - pd.Timedelta(days=lookback_days)]
    n_days = max(recent["date"].nunique(), 1)
    daily = recent.groupby(ADSET_KEYS)["spend"].sum() / n_days
    full = df.groupby(ADSET_KEYS)[["spend", "revenue"]].sum()
    roas = (full.revenue / full.spend.replace(0, np.nan)).fillna(0)

    cuts, gains = {}, {}
    for key in daily.index:
        if full.loc[key, "spend"] < min_spend:
            continue
        if roas[key] < breakeven:
            cuts[key] = daily[key] * max_shift_pct
        elif roas[key] >= breakeven * winner_mult:
            gains[key] = daily[key] * max_shift_pct  # cap per winner
    pool = sum(cuts.values())
    weights = {k: (roas[k] - breakeven) * daily[k] for k in gains}
    wsum = sum(weights.values())
    alloc = {}
    remaining = pool
    # proportional split, respecting per-winner caps (iterate to redistribute overflow)
    active = dict(weights)
    for _ in range(len(active) + 1):
        if not active or remaining <= 1e-9:
            break
        tot = sum(active.values())
        overflow = False
        for k in list(active):
            share = remaining * active[k] / tot
            room = gains[k] - alloc.get(k, 0.0)
            if share >= room - 1e-12:
                alloc[k] = alloc.get(k, 0.0) + room
                remaining -= room
                del active[k]
                overflow = True
        if not overflow:
            for k, w in active.items():
                alloc[k] = alloc.get(k, 0.0) + remaining * w / tot
            remaining = 0.0
            break
    moved = sum(alloc.values())
    # scale cuts down if the winners cannot absorb the whole pool
    scale = (moved / pool) if pool > 0 else 0.0
    moves = []
    for k, c in cuts.items():
        cut = c * scale
        if cut > 0.005:
            moves.append({**dict(zip(ADSET_KEYS, k)), "action": "decrease", "roas": _r(roas[k], 2),
                          "current_daily": _r(daily[k], 2), "change_daily": _r(-cut, 2),
                          "proposed_daily": _r(daily[k] - cut, 2),
                          "change_pct": _r(-cut / daily[k] * 100, 1)})
    for k, a in alloc.items():
        if a > 0.005:
            moves.append({**dict(zip(ADSET_KEYS, k)), "action": "increase", "roas": _r(roas[k], 2),
                          "current_daily": _r(daily[k], 2), "change_daily": _r(a, 2),
                          "proposed_daily": _r(daily[k] + a, 2),
                          "change_pct": _r(a / daily[k] * 100, 1)})
    est = 0.0
    if moved > 0 and cuts:
        cut_roas = sum(roas[k] * cuts[k] for k in cuts) / pool
        win_roas = sum(roas[k] * alloc[k] for k in alloc) / moved
        est = moved * (win_roas - cut_roas)
    return {
        "max_shift_pct": max_shift_pct, "breakeven_roas": breakeven, "lookback_days": lookback_days,
        "total_daily_budget": _r(daily.sum(), 2), "moved_daily": _r(moved, 2),
        "moves": sorted(moves, key=lambda m: (m["action"], m["roas"])),
        "est_daily_revenue_delta": _r(est, 2),
        "note": "Estimate assumes historical ROAS holds at the new spend level, which it often does not "
                "(diminishing returns). Apply gradually and re-check. AdPilot does not change budgets.",
    }


# ------------------------------------------------------------------ A/B testing
def ab_test_significance(
    a_successes: int, a_trials: int, b_successes: int, b_trials: int, alpha: float = 0.05
) -> dict:
    """Two-sided two-proportion z-test (pooled) for CTR (clicks/impressions) or CVR (purchases/clicks)."""
    if min(a_trials, b_trials) <= 0:
        raise ValueError("trials must be positive")
    if a_successes > a_trials or b_successes > b_trials or min(a_successes, b_successes) < 0:
        raise ValueError("successes must be between 0 and trials")
    p1, p2 = a_successes / a_trials, b_successes / b_trials
    pool = (a_successes + b_successes) / (a_trials + b_trials)
    se = math.sqrt(pool * (1 - pool) * (1 / a_trials + 1 / b_trials))
    z = (p2 - p1) / se if se > 0 else 0.0
    p_value = math.erfc(abs(z) / math.sqrt(2))
    se_diff = math.sqrt(p1 * (1 - p1) / a_trials + p2 * (1 - p2) / b_trials)
    diff = p2 - p1
    significant = p_value < alpha
    return {
        "rate_a": _r(p1, 5), "rate_b": _r(p2, 5), "abs_diff": _r(diff, 5),
        "relative_lift_pct": _r(diff / p1 * 100, 2) if p1 else None,
        "z": _r(z, 3), "p_value": _r(p_value, 5), "alpha": alpha, "significant": significant,
        "ci95_diff": [_r(diff - 1.96 * se_diff, 5), _r(diff + 1.96 * se_diff, 5)],
        "verdict": (f"B is {'better' if diff > 0 else 'worse'} than A (p={p_value:.4f})" if significant
                    else f"No significant difference at alpha={alpha} (p={p_value:.4f}); keep testing or call it a tie"),
    }


def ab_test_ads(df: pd.DataFrame, ad_a: str, ad_b: str, metric: str = "ctr", alpha: float = 0.05) -> dict:
    """Convenience wrapper: run the z-test between two ads by name on CTR or CVR."""
    if metric not in ("ctr", "cvr"):
        raise ValueError("metric must be 'ctr' or 'cvr'")
    num, den = ("clicks", "impressions") if metric == "ctr" else ("purchases", "clicks")
    sums = []
    for name in (ad_a, ad_b):
        sub = df[df["ad"] == name]
        if sub.empty:
            raise ValueError(f"Ad '{name}' not found")
        sums.append((int(sub[num].sum()), int(sub[den].sum())))
    res = ab_test_significance(sums[0][0], sums[0][1], sums[1][0], sums[1][1], alpha)
    return {"ad_a": ad_a, "ad_b": ad_b, "metric": metric, **res}
