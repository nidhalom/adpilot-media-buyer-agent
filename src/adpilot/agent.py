"""The AdPilot agent: Claude with a manual tool-use loop, plus a deterministic offline planner.

SAFETY: the agent only analyses data you give it and RECOMMENDS actions. It has no access to
live ad accounts and no tool that can change budgets, pause ads or publish creatives.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from . import hooks as hooks_mod
from . import tools
from .report import render_offline_report

MODEL = "claude-opus-5-5"
MAX_ITERATIONS = 14

SYSTEM_PROMPT = """You are AdPilot, a senior performance media buyer (Meta, Google, TikTok).
You are given an ads export that was already loaded for you. Use your tools to analyse it, then
write the final report in Markdown for the advertiser.

Rules:
- You only RECOMMEND. You cannot and must not claim to change budgets, pause ads or touch any ad account.
- Always compute break-even ROAS from the margin first and judge performance against it, not against a generic 'good ROAS'.
- Respect the minimum-spend guard: never call an ad a winner or loser from tiny spend.
- Call these tools: compute_kpis (overall and by platform), breakeven_roas, find_winners_losers,
  detect_creative_fatigue, propose_budget_reallocation, ab_test (for pairs of ads in the same ad set),
  and generate_ad_hooks (for fatigued or top ads). Base every number in the report on tool outputs.
- Report structure: Executive summary, What to kill, What to scale, Fatigued creatives, Budget moves,
  A/B test verdicts, New hooks to test, Caveats. Be concrete and brief. Use tables where useful.
- State clearly when a difference is not statistically significant."""

TOOL_SPECS: list[dict] = [
    {
        "name": "compute_kpis",
        "description": "Compute CTR, CPC, CPM, CPA, ROAS, CVR from summed totals, overall or grouped by columns "
                       "(platform, campaign, adset, ad).",
        "input_schema": {"type": "object", "properties": {
            "group_by": {"type": "array", "items": {"type": "string", "enum": ["platform", "campaign", "adset", "ad"]}}}},
    },
    {
        "name": "breakeven_roas",
        "description": "Break-even ROAS = 1 / gross margin. Defaults to the margin supplied for this run.",
        "input_schema": {"type": "object", "properties": {"margin": {"type": "number", "description": "fraction, e.g. 0.35"}}},
    },
    {
        "name": "find_winners_losers",
        "description": "Classify ads as winners / losers / borderline vs break-even ROAS, with a minimum-spend guard "
                       "(ads below it are 'insufficient_data').",
        "input_schema": {"type": "object", "properties": {
            "min_spend": {"type": "number"}, "level": {"type": "string", "enum": ["ad", "adset"]}}},
    },
    {
        "name": "detect_creative_fatigue",
        "description": "Find ads whose rolling CTR decayed from peak while frequency is high.",
        "input_schema": {"type": "object", "properties": {
            "window": {"type": "integer"}, "freq_threshold": {"type": "number"}, "decay_threshold": {"type": "number"}}},
    },
    {
        "name": "propose_budget_reallocation",
        "description": "Propose (not apply) a daily budget shift from below-break-even ad sets to top performers, "
                       "capped at max_shift_pct of each ad set's daily budget.",
        "input_schema": {"type": "object", "properties": {"max_shift_pct": {"type": "number"}}},
    },
    {
        "name": "ab_test",
        "description": "Two-proportion z-test between two ads (by exact ad name) on CTR or CVR.",
        "input_schema": {"type": "object", "properties": {
            "ad_a": {"type": "string"}, "ad_b": {"type": "string"},
            "metric": {"type": "string", "enum": ["ctr", "cvr"]}}, "required": ["ad_a", "ad_b"]},
    },
    {
        "name": "generate_ad_hooks",
        "description": "Generate new ad hooks to test for a product and creative angle.",
        "input_schema": {"type": "object", "properties": {
            "product": {"type": "string"}, "angle": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["product"]},
    },
]


@dataclass
class ToolContext:
    df: pd.DataFrame
    margin: float
    product: str = "your product"
    hook_llm: Callable[[str], str] | None = None


@dataclass
class AgentResult:
    report: str
    mode: str  # "llm" or "offline"
    trace: list[dict] = field(default_factory=list)  # [{"tool":..., "input":..., "ok":..., "output":...}]


def run_tool(ctx: ToolContext, name: str, args: dict) -> Any:
    """Dispatch a tool call; returns JSON-serialisable output. Raises on bad input."""
    if name == "compute_kpis":
        return tools.compute_kpis(ctx.df, args.get("group_by") or None)
    if name == "breakeven_roas":
        return {"margin": args.get("margin", ctx.margin), "breakeven_roas": tools.breakeven_roas(args.get("margin", ctx.margin))}
    if name == "find_winners_losers":
        return tools.find_winners_losers(ctx.df, tools.breakeven_roas(ctx.margin),
                                         min_spend=args.get("min_spend", 300.0), level=args.get("level", "ad"))
    if name == "detect_creative_fatigue":
        res = tools.detect_creative_fatigue(
            ctx.df, window=int(args.get("window", 7)), freq_threshold=args.get("freq_threshold", 3.0),
            decay_threshold=args.get("decay_threshold", 0.25))
        return [{k: v for k, v in r.items() if k != "series"} for r in res]
    if name == "propose_budget_reallocation":
        return tools.propose_budget_reallocation(ctx.df, tools.breakeven_roas(ctx.margin),
                                                 max_shift_pct=args.get("max_shift_pct", 0.20))
    if name == "ab_test":
        return tools.ab_test_ads(ctx.df, args["ad_a"], args["ad_b"], args.get("metric", "ctr"))
    if name == "generate_ad_hooks":
        return hooks_mod.generate_ad_hooks(args.get("product") or ctx.product, args.get("angle", ""),
                                           int(args.get("n", 5)), llm=ctx.hook_llm)
    raise ValueError(f"Unknown tool '{name}'")


def _call(ctx: ToolContext, trace: list[dict], name: str, args: dict) -> Any:
    try:
        out = run_tool(ctx, name, args)
        trace.append({"tool": name, "input": args, "ok": True, "output": out})
        return out
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as is_error
        trace.append({"tool": name, "input": args, "ok": False, "output": str(exc)})
        raise


def _json(x: Any) -> str:
    return json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o))


# --------------------------------------------------------------------- offline
def run_offline(df: pd.DataFrame, margin: float, product: str = "your product") -> AgentResult:
    """Deterministic planner: fixed, sensible tool order, then a report template."""
    ctx = ToolContext(df=df, margin=margin, product=product)
    trace: list[dict] = []
    res: dict[str, Any] = {"margin": margin, "product": product}
    res["overall"] = _call(ctx, trace, "compute_kpis", {})[0]
    res["by_platform"] = _call(ctx, trace, "compute_kpis", {"group_by": ["platform"]})
    res["breakeven"] = _call(ctx, trace, "breakeven_roas", {})["breakeven_roas"]
    res["wl"] = _call(ctx, trace, "find_winners_losers", {})
    res["fatigue"] = _call(ctx, trace, "detect_creative_fatigue", {})
    res["realloc"] = _call(ctx, trace, "propose_budget_reallocation", {})

    # A/B: top-2 ads by spend inside each ad set that has >=2 ads; keep 3 biggest pairs.
    spend = df.groupby(["platform", "campaign", "adset", "ad"])["spend"].sum().reset_index()
    pairs = []
    for (_, _, _), g in spend.groupby(["platform", "campaign", "adset"]):
        if len(g) >= 2:
            top = g.sort_values("spend", ascending=False).head(2)
            pairs.append((float(top.spend.sum()), top.ad.iloc[0], top.ad.iloc[1]))
    res["ab"] = []
    for _, a, b in sorted(pairs, reverse=True)[:3]:
        res["ab"].append(_call(ctx, trace, "ab_test", {"ad_a": a, "ad_b": b, "metric": "ctr"}))

    targets = [f["ad"] for f in res["fatigue"] if f["status"] == "fatigued"][:2]
    if not targets and res["wl"]["winners"]:
        targets = [res["wl"]["winners"][0]["ad"]]
    res["hooks"] = [
        {"ad": ad, **_call(ctx, trace, "generate_ad_hooks",
                           {"product": product, "angle": hooks_mod.infer_angle(ad), "n": 3})}
        for ad in targets
    ]
    res["rows"] = len(df)
    res["date_min"], res["date_max"] = df["date"].min(), df["date"].max()
    return AgentResult(report=render_offline_report(res, trace), mode="offline", trace=trace)


# ------------------------------------------------------------------------ LLM
def make_hook_llm(client: Any, model: str = MODEL) -> Callable[[str], str]:
    def _llm(prompt: str) -> str:
        resp = client.messages.create(model=model, max_tokens=2000, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return _llm


def run_llm(client: Any, df: pd.DataFrame, margin: float, product: str = "your product",
            model: str = MODEL, max_iterations: int = MAX_ITERATIONS) -> AgentResult:
    """Manual tool-use loop: the model decides which tools to call and writes the report."""
    ctx = ToolContext(df=df, margin=margin, product=product, hook_llm=make_hook_llm(client, model))
    trace: list[dict] = []
    brief = (
        f"Ads export loaded: {len(df)} rows, {df['date'].min():%Y-%m-%d} to {df['date'].max():%Y-%m-%d}, "
        f"platforms: {', '.join(sorted(df['platform'].unique()))}, {df['ad'].nunique()} distinct ads. "
        f"Gross margin: {margin:.0%}. Product: {product}. Analyse it and write the media-buyer report."
    )
    messages: list[dict] = [{"role": "user", "content": brief}]
    for _ in range(max_iterations):
        response = client.messages.create(model=model, max_tokens=16000, system=SYSTEM_PROMPT,
                                          tools=TOOL_SPECS, messages=messages)
        if response.stop_reason == "refusal":
            return AgentResult(report="The model declined to produce this analysis.", mode="llm", trace=trace)
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            return AgentResult(report=text, mode="llm", trace=trace)
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            try:
                out = _call(ctx, trace, block.name, dict(block.input))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": _json(out)})
            except Exception as exc:  # noqa: BLE001
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"Error: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"Agent did not finish within {max_iterations} iterations")


def analyze(df: pd.DataFrame, margin: float, product: str = "your product",
            offline: bool | None = None, client: Any = None) -> AgentResult:
    """Run the agent. Offline when no API key (or offline=True); otherwise Claude."""
    if client is None and not offline and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic  # imported lazily so offline mode never needs a key

        client = anthropic.Anthropic()
    if offline or client is None:
        return run_offline(df, margin, product)
    return run_llm(client, df, margin, product)
