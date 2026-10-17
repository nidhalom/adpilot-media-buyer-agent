import math

import pandas as pd
import pytest

from adpilot import tools
from conftest import make_rows


def test_compute_kpis_totals():
    df = make_rows(days=1, impr=10000, ctr=0.02, cvr=0.05, cpm=10, aov=50)  # 200 clicks, 10 purchases
    k = tools.compute_kpis(df)[0]
    assert k["ctr"] == pytest.approx(0.02) and k["cpm"] == pytest.approx(10)
    assert k["cpc"] == pytest.approx(0.5) and k["cpa"] == pytest.approx(10)
    assert k["roas"] == pytest.approx(5.0) and k["cvr"] == pytest.approx(0.05)


def test_compute_kpis_zero_division_and_grouping():
    df = make_rows(days=1, ctr=0.0)
    k = tools.compute_kpis(df)[0]
    assert k["cpc"] is None and k["cpa"] is None and k["cvr"] is None
    two = pd.concat([make_rows(ad="A"), make_rows(ad="B", ctr=0.04)])
    g = tools.compute_kpis(two, ["ad"])
    assert {x["ad"] for x in g} == {"A", "B"}
    with pytest.raises(ValueError):
        tools.compute_kpis(two, ["nope"])


def test_breakeven():
    assert tools.breakeven_roas(0.5) == 2.0
    assert tools.breakeven_roas(0.35) == pytest.approx(2.8571, abs=1e-3)
    for bad in (0, -1, 1.5):
        with pytest.raises(ValueError):
            tools.breakeven_roas(bad)


def test_fatigue_detected_vs_healthy():
    healthy = make_rows(ad="ok", freq=1.5)
    fat = make_rows(ad="tired", freq=1.5)
    fat["clicks"] = [200] * 7 + [100] * 4 + [40] * 3
    fat["frequency"] = [1.5 + i * 0.25 for i in range(len(fat))]
    res = {r["ad"]: r for r in tools.detect_creative_fatigue(pd.concat([healthy, fat]))}
    assert res["ok"]["status"] == "healthy"
    assert res["tired"]["status"] == "fatigued"
    assert res["tired"]["ctr_decay_pct"] >= 25 and res["tired"]["latest_frequency"] >= 3


def test_fatigue_decay_without_frequency_is_at_risk():
    d = make_rows(ad="g", platform="google", freq=float("nan"))
    d["clicks"] = [200] * 7 + [60] * 7
    r = tools.detect_creative_fatigue(d)[0]
    assert r["status"] == "at_risk" and r["latest_frequency"] is None


def test_fatigue_skips_short_history():
    assert tools.detect_creative_fatigue(make_rows(days=5)) == []


def test_winners_losers_with_spend_guard():
    win = make_rows(ad="win", ctr=0.02, cvr=0.05, aov=50)  # roas 5
    lose = make_rows(ad="lose", ctr=0.02, cvr=0.01, aov=50)  # roas 1
    tiny = make_rows(ad="tiny", days=1, impr=1000, ctr=0.05, cvr=0.5, aov=100)  # spend 10
    r = tools.find_winners_losers(pd.concat([win, lose, tiny]), breakeven=2.0, min_spend=300)
    assert [x["ad"] for x in r["winners"]] == ["win"]
    assert [x["ad"] for x in r["losers"]] == ["lose"]
    assert [x["ad"] for x in r["insufficient_data"]] == ["tiny"]


def _realloc_df():
    return pd.concat([
        make_rows(ad="w", adset="W", ctr=0.02, cvr=0.05, aov=50),  # roas 5
        make_rows(ad="l", adset="L", ctr=0.02, cvr=0.01, aov=50),  # roas 1
        make_rows(ad="m", adset="M", ctr=0.02, cvr=0.02, aov=55),  # roas 2.2 (neutral)
    ])


def test_reallocation_caps_and_conservation():
    r = tools.propose_budget_reallocation(_realloc_df(), breakeven=2.0, max_shift_pct=0.2)
    inc = [m for m in r["moves"] if m["action"] == "increase"]
    dec = [m for m in r["moves"] if m["action"] == "decrease"]
    assert [m["adset"] for m in inc] == ["W"] and [m["adset"] for m in dec] == ["L"]
    for m in r["moves"]:
        assert abs(m["change_pct"]) <= 20.0 + 1e-6
    assert sum(m["change_daily"] for m in inc) == pytest.approx(-sum(m["change_daily"] for m in dec), abs=0.02)


def test_reallocation_small_cap_and_validation():
    r = tools.propose_budget_reallocation(_realloc_df(), breakeven=2.0, max_shift_pct=0.05)
    assert r["moves"] and all(abs(m["change_pct"]) <= 5.0 + 1e-6 for m in r["moves"])
    with pytest.raises(ValueError):
        tools.propose_budget_reallocation(_realloc_df(), 2.0, max_shift_pct=0)


def test_reallocation_no_winners_means_no_moves():
    df = pd.concat([make_rows(ad="l", adset="L", cvr=0.01, aov=50), make_rows(ad="m", adset="M", cvr=0.02, aov=50)])
    r = tools.propose_budget_reallocation(df, breakeven=2.0)
    assert r["moves"] == [] and r["moved_daily"] == 0


def test_ab_known_value():
    r = tools.ab_test_significance(100, 1000, 150, 1000)
    pool = 250 / 2000
    z = 0.05 / math.sqrt(pool * (1 - pool) * 2 / 1000)
    assert r["z"] == pytest.approx(z, abs=1e-3)
    assert r["p_value"] == pytest.approx(math.erfc(z / math.sqrt(2)), abs=1e-4)
    assert r["significant"] and r["relative_lift_pct"] == 50.0


def test_ab_null_and_errors():
    assert not tools.ab_test_significance(100, 1000, 101, 1000)["significant"]
    assert tools.ab_test_significance(0, 100, 0, 100)["p_value"] == 1.0
    with pytest.raises(ValueError):
        tools.ab_test_significance(5, 0, 1, 10)
    with pytest.raises(ValueError):
        tools.ab_test_significance(11, 10, 1, 10)


def test_ab_test_ads_wrapper():
    df = pd.concat([make_rows(ad="a", ctr=0.01), make_rows(ad="b", ctr=0.02)])
    assert tools.ab_test_ads(df, "a", "b", "ctr")["significant"]
    with pytest.raises(ValueError):
        tools.ab_test_ads(df, "a", "zzz")
    with pytest.raises(ValueError):
        tools.ab_test_ads(df, "a", "b", "roas")


def test_synthetic_finds_planted_patterns(df):
    fat = {r["ad"] for r in tools.detect_creative_fatigue(df) if r["status"] == "fatigued"}
    assert {"Hook_ASMR_Unboxing", "Founder_Story_Video"} <= fat
    wl = tools.find_winners_losers(df, tools.breakeven_roas(0.35))
    assert "Static_Promo" in {x["ad"] for x in wl["losers"]}
    assert "UGC_Testimonial_V1" in {x["ad"] for x in wl["winners"]}
