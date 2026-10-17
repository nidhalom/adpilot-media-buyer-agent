import pandas as pd
import pytest

from adpilot import synthetic


@pytest.fixture(scope="session")
def df() -> pd.DataFrame:
    return synthetic.generate(seed=42)


def make_rows(ad="A", days=14, impr=10000, ctr=0.02, cvr=0.03, cpm=10.0, aov=60.0, freq=1.5,
              platform="meta", adset="S1", campaign="C1", start="2025-01-01"):
    rows = []
    for d in range(days):
        clicks = round(impr * ctr)
        purchases = round(clicks * cvr)
        rows.append(dict(date=pd.Timestamp(start) + pd.Timedelta(days=d), platform=platform,
                         campaign=campaign, adset=adset, ad=ad, spend=impr * cpm / 1000,
                         impressions=impr, clicks=clicks, purchases=purchases,
                         revenue=purchases * aov, frequency=freq))
    return pd.DataFrame(rows)
