"""Markdown report template used by the offline planner."""

from __future__ import annotations

import json


def _f(x, nd=2, pct=False):
    if x is None:
        return "n/a"
    return f"{x * 100:.{nd}f}%" if pct else f"{x:,.{nd}f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None._\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _name(r: dict) -> str:
    return f"{r['ad']} ({r['platform']})"


def render_offline_report(res: dict, trace: list[dict]) -> str:
    o, be = res["overall"], res["breakeven"]
    wl, fat, re_ = res["wl"], res["fatigue"], res["realloc"]
    L: list[str] = []
    L.append("# AdPilot media-buyer report\n")
    L.append(f"_Mode: offline deterministic planner (no LLM). Data: {res['rows']} rows, "
             f"{res['date_min']:%Y-%m-%d} to {res['date_max']:%Y-%m-%d}. Gross margin {res['margin']:.0%}._\n")
    L.append("> AdPilot only **recommends**. It has no access to live ad accounts and never changes budgets, "
             "pauses ads or publishes anything. You apply (or ignore) every action yourself.\n")

    L.append("## Executive summary\n")
    verdict = "above" if (o["roas"] or 0) >= be else "below"
    L.append(f"- Blended ROAS is **{_f(o['roas'])}** on spend of {_f(o['spend'], 0)}, "
             f"{verdict} the break-even ROAS of **{_f(be)}** (1 / {res['margin']:.0%} margin).")
    L.append(f"- **{len(wl['losers'])} ads to kill**, **{len(wl['winners'])} to scale**, "
             f"{len(wl['borderline'])} borderline, {len(wl['insufficient_data'])} with too little spend to judge "
             f"(guard: {_f(wl['min_spend'], 0)} spend).")
    nf = sum(1 for f in fat if f["status"] == "fatigued")
    na = sum(1 for f in fat if f["status"] == "at_risk")
    L.append(f"- **{nf} fatigued** and {na} at-risk creatives.")
    L.append(f"- Proposed budget move: {_f(re_['moved_daily'])} per day "
             f"(max {re_['max_shift_pct']:.0%} per ad set per day).\n")

    L.append("## Account snapshot\n")
    rows = [[p["group"], _f(p["spend"], 0), _f(p["roas"]), _f(p["cpa"]), _f(p["ctr"], 2, True),
             _f(p["cpm"]), _f(p["cvr"], 2, True)] for p in res["by_platform"]]
    rows.append(["**all**", _f(o["spend"], 0), _f(o["roas"]), _f(o["cpa"]), _f(o["ctr"], 2, True),
                 _f(o["cpm"]), _f(o["cvr"], 2, True)])
    L.append(_table(["Platform", "Spend", "ROAS", "CPA", "CTR", "CPM", "CVR"], rows))

    L.append("## What to kill\n")
    L.append(f"ROAS below {_f(be * 0.8)} (80% of break-even) with enough spend to trust it.\n")
    L.append(_table(["Ad", "Spend", "ROAS", "CPA", "CTR", "CVR"],
                    [[_name(r), _f(r["spend"], 0), _f(r["roas"]), _f(r["cpa"]), _f(r["ctr"], 2, True),
                      _f(r["cvr"], 2, True)] for r in wl["losers"]]))

    L.append("## What to scale\n")
    L.append(f"ROAS at least {_f(be * 1.2)} (120% of break-even).\n")
    L.append(_table(["Ad", "Spend", "ROAS", "CPA", "CTR", "CVR"],
                    [[_name(r), _f(r["spend"], 0), _f(r["roas"]), _f(r["cpa"]), _f(r["ctr"], 2, True),
                      _f(r["cvr"], 2, True)] for r in wl["winners"]]))
    if wl["borderline"]:
        L.append("Borderline (between 80% and 120% of break-even; let them run or iterate the creative): "
                 + ", ".join(_name(r) + f" ({_f(r['roas'])})" for r in wl["borderline"]) + ".\n")
    if wl["insufficient_data"]:
        L.append("Not enough spend to judge: " + ", ".join(_name(r) for r in wl["insufficient_data"]) + ".\n")

    L.append("## Fatigued creatives\n")
    L.append("Rolling 7-day CTR versus its own peak, plus latest frequency. "
             "'Fatigued' = decay >= 25% and frequency >= 3.0; 'at risk' = one of the two.\n")
    L.append(_table(["Ad", "Status", "CTR decay from peak", "Latest freq.", "Rolling CTR now"],
                    [[_name(f), f["status"], f"{_f(f['ctr_decay_pct'], 1)}%", _f(f["latest_frequency"]),
                      _f(f["ctr_latest_rolling"], 2, True)] for f in fat if f["status"] != "healthy"]))
    L.append("Action: refresh the creative (new hook and first 3 seconds, same offer) rather than raising budget on it.\n")

    L.append("## Budget moves (proposal)\n")
    L.append(f"Cuts and increases are capped at {re_['max_shift_pct']:.0%} of each ad set's recent daily budget "
             f"(last {re_['lookback_days']} days). Total daily budget is unchanged.\n")
    L.append(_table(["Ad set", "Action", "ROAS", "Now / day", "Change / day", "Proposed / day"],
                    [[f"{m['adset']} ({m['platform']})", m["action"], _f(m["roas"]), _f(m["current_daily"]),
                      f"{m['change_daily']:+,.2f} ({m['change_pct']:+.1f}%)", _f(m["proposed_daily"])]
                     for m in re_["moves"]]))
    L.append(f"_{re_['note']}_ Estimated daily revenue delta at historical ROAS: {_f(re_['est_daily_revenue_delta'])}.\n")

    L.append("## A/B test verdicts (CTR, two-proportion z-test)\n")
    L.append(_table(["A", "B", "CTR A", "CTR B", "Lift", "p-value", "Verdict"],
                    [[t["ad_a"], t["ad_b"], _f(t["rate_a"], 2, True), _f(t["rate_b"], 2, True),
                      f"{_f(t['relative_lift_pct'], 1)}%", _f(t["p_value"], 4), t["verdict"]] for t in res["ab"]]))

    L.append("## New hooks to test\n")
    if res["hooks"]:
        for h in res["hooks"]:
            L.append(f"**For `{h['ad']}`** ({h['source']}-generated, angle: {h['angle']}):")
            L.extend(f"- {x}" for x in h["hooks"])
            L.append("")
    else:
        L.append("_No fatigued or winning ads to base hooks on._\n")

    L.append("## Caveats\n")
    L.append("- Attribution is whatever the platform exported (view-through, windows and double counting differ by platform).")
    L.append("- ROAS is revenue / spend; margin is applied only through the break-even threshold.")
    L.append("- Statistical tests treat impressions as independent; real delivery is not, so treat p-values as a guide.\n")

    L.append("## Appendix: tool calls\n")
    L.append(_table(["#", "Tool", "Input", "OK"],
                    [[i + 1, t["tool"], f"`{json.dumps(t['input'])}`", "yes" if t["ok"] else "no"]
                     for i, t in enumerate(trace)]))
    return "\n".join(L)
