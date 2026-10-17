from fastapi.testclient import TestClient

from adpilot import cli
from adpilot.web import app


def test_cli_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["sample", "--out-dir", str(tmp_path)]) == 0
    out = tmp_path / "r.md"
    assert cli.main(["analyze", str(tmp_path / "sample.csv"), "--margin", "0.35", "--out", str(out)]) == 0
    assert "# AdPilot media-buyer report" in out.read_text(encoding="utf-8")
    exports = [str(p) for p in tmp_path.glob("synthetic_*_export.csv")]
    assert len(exports) == 3
    assert cli.main(["analyze", *exports, "--margin", "0.4", "--offline", "--out", str(tmp_path / "r2.md")]) == 0


def test_cli_bad_input(tmp_path, capsys):
    bad = tmp_path / "b.csv"
    bad.write_text("foo,bar\n1,2\n")
    assert cli.main(["analyze", str(bad), "--margin", "0.3"]) == 2
    assert "error" in capsys.readouterr().err


def test_web_endpoints(df):
    c = TestClient(app)
    assert "AdPilot" in c.get("/").text
    j = c.get("/api/sample").json()
    assert j["breakeven_roas"] > 2.8 and j["ads"] and j["fatigue"] and "report_md" in j
    csv = df.assign(date=df.date.dt.strftime("%Y-%m-%d")).to_csv(index=False)
    assert c.post("/api/analyze?margin=0.5", content=csv).json()["breakeven_roas"] == 2.0
    assert c.post("/api/analyze", content="foo,bar\n1,2\n").status_code == 400
