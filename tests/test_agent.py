import json
from types import SimpleNamespace as NS

import pytest

from adpilot import agent


def tu(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def resp(content, stop):
    return NS(content=content, stop_reason=stop)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic; records every request."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = self

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.script.pop(0)


def test_loop_runs_tools_and_returns_report(df):
    client = FakeClient([
        resp([NS(type="text", text="Checking."), tu("t1", "breakeven_roas"),
              tu("t2", "compute_kpis", group_by=["platform"])], "tool_use"),
        resp([tu("t3", "ab_test", ad_a="Static_Promo", ad_b="Hook_ASMR_Unboxing", metric="ctr")], "tool_use"),
        resp([NS(type="text", text="# Report\nKill Static_Promo.")], "end_turn"),
    ])
    r = agent.run_llm(client, df, 0.35)
    assert r.mode == "llm" and r.report.startswith("# Report")
    assert [t["tool"] for t in r.trace] == ["breakeven_roas", "compute_kpis", "ab_test"]
    # the second request carries ONE user message holding both tool_results
    msgs = client.calls[1]["messages"]
    assert msgs[1]["role"] == "assistant" and msgs[2]["role"] == "user"
    results = msgs[2]["content"]
    assert [x["tool_use_id"] for x in results] == ["t1", "t2"]
    assert json.loads(results[0]["content"])["breakeven_roas"] == pytest.approx(2.857, abs=1e-3)
    c = client.calls[0]
    assert c["model"] == "claude-opus-5-5" and c["max_tokens"] == 16000
    assert "thinking" not in c and "tool_choice" not in c
    assert {t["name"] for t in c["tools"]} >= {"compute_kpis", "detect_creative_fatigue", "generate_ad_hooks"}


def test_tool_error_reported_as_is_error(df):
    client = FakeClient([
        resp([tu("e1", "ab_test", ad_a="nope", ad_b="nada")], "tool_use"),
        resp([tu("e2", "no_such_tool")], "tool_use"),
        resp([NS(type="text", text="done")], "end_turn"),
    ])
    r = agent.run_llm(client, df, 0.35)
    assert r.report == "done"
    assert client.calls[1]["messages"][2]["content"][0]["is_error"] is True
    assert client.calls[2]["messages"][4]["content"][0]["is_error"] is True
    assert [t["ok"] for t in r.trace] == [False, False]


def test_refusal_and_iteration_cap(df):
    r = agent.run_llm(FakeClient([resp([], "refusal")]), df, 0.35)
    assert "declined" in r.report
    loop = FakeClient([resp([tu(f"x{i}", "breakeven_roas")], "tool_use") for i in range(5)])
    with pytest.raises(RuntimeError):
        agent.run_llm(loop, df, 0.35, max_iterations=3)


def test_hook_tool_uses_llm_when_available(df):
    client = FakeClient([
        resp([tu("h", "generate_ad_hooks", product="serum", angle="asmr", n=2)], "tool_use"),
        NS(content=[NS(type="text", text="hook A\nhook B")], stop_reason="end_turn"),  # nested hook call
        resp([NS(type="text", text="ok")], "end_turn"),
    ])
    r = agent.run_llm(client, df, 0.35)
    out = r.trace[0]["output"]
    assert out["source"] == "llm" and out["hooks"] == ["hook A", "hook B"]


def test_offline_report_deterministic_and_complete(df):
    a, b = agent.run_offline(df, 0.35), agent.run_offline(df, 0.35)
    assert a.report == b.report and a.mode == "offline"
    for section in ("Executive summary", "What to kill", "What to scale", "Fatigued creatives",
                    "Budget moves", "A/B test verdicts", "New hooks to test", "only **recommends**"):
        assert section in a.report
    assert "Static_Promo" in a.report
    assert all(t["ok"] for t in a.trace)


def test_analyze_without_key_is_offline(df, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert agent.analyze(df, 0.35).mode == "offline"
    fake = FakeClient([resp([NS(type="text", text="x")], "end_turn")])
    assert agent.analyze(df, 0.35, client=fake).mode == "llm"


def test_no_tool_can_mutate_accounts():
    banned = ("pause", "apply", "update", "delete", "publish")
    assert not any(w in t["name"] for t in agent.TOOL_SPECS for w in banned)
