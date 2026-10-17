import pandas as pd
import pytest

from adpilot import ingest, synthetic


def test_meta_headers(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "Day,Campaign name,Ad set name,Ad name,Amount spent (USD),Impressions,Link clicks,"
        "Purchases,Purchase conversion value,Frequency\n"
        '2025-01-01,C,S,A,"$1,200.50","10,000",200,5,400,1.4\n'
    )
    df = ingest.load_csv(p)
    assert list(df.columns) == ingest.SCHEMA
    r = df.iloc[0]
    assert r.platform == "meta" and r.spend == 1200.5 and r.impressions == 10000 and r.frequency == 1.4


def test_google_title_rows_and_total(tmp_path):
    out = synthetic.write_platform_exports(synthetic.generate(), tmp_path)
    g = next(p for p in out if "google" in p.name)
    df = ingest.load_csv(g)
    assert set(df.platform) == {"google"}
    assert df.frequency.isna().all()
    assert len(df) == 4 * 28  # total row dropped, thousands separators parsed
    assert df.impressions.min() > 0


def test_tiktok_headers(tmp_path):
    out = synthetic.write_platform_exports(synthetic.generate(), tmp_path)
    t = next(p for p in out if "tiktok" in p.name)
    df = ingest.load_csv(t)
    assert set(df.platform) == {"tiktok"} and df.revenue.sum() > 0


def test_load_many_matches_unified(tmp_path):
    d = synthetic.generate()
    out = synthetic.write_platform_exports(d, tmp_path)
    combined = ingest.load_many([p for p in out if "export" in p.name])
    unified = ingest.load_csv(tmp_path / "sample.csv")
    assert len(combined) == len(unified) == len(d)
    assert combined.spend.sum() == pytest.approx(unified.spend.sum())


def test_missing_columns():
    with pytest.raises(ValueError):
        ingest.normalise(pd.DataFrame({"foo": [1]}))


def test_synthetic_is_seeded():
    assert synthetic.generate(1).equals(synthetic.generate(1))
    assert not synthetic.generate(1).equals(synthetic.generate(2))
