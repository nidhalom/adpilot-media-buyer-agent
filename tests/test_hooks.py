from adpilot import hooks


def test_templates_deterministic_and_angle():
    a = hooks.generate_ad_hooks("serum", "asmr", 3)
    assert a == hooks.generate_ad_hooks("serum", "asmr", 3)
    assert a["source"] == "template" and len(a["hooks"]) == 3 and "serum" in " ".join(a["hooks"])
    assert hooks.infer_angle("Founder_Story_Video") == "founder"


def test_llm_used_and_fallback():
    r = hooks.generate_ad_hooks("x", "y", 2, llm=lambda p: "- one\n- two\n- three")
    assert r["source"] == "llm" and r["hooks"] == ["one", "two"]
    r = hooks.generate_ad_hooks("x", "y", 2, llm=lambda p: "")
    assert r["source"] == "template"
