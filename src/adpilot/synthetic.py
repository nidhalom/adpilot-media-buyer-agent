"""Seeded SYNTHETIC ads data generator.

Everything produced here is made up. No real client, account or campaign data is
included anywhere in this repository. The ads are designed to contain known
patterns (clear winners, clear losers, creative fatigue, a real and a null A/B
difference) so the tools have something to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp("2025-03-03")
DAYS = 28


@dataclass
class AdSpec:
    platform: str
    campaign: str
    adset: str
    ad: str
    impr_per_day: int
    cpm: float
    ctr: float
    cvr: float
    aov: float
    fatigue_start: int | None = None  # day index where CTR starts to decay
    fatigue_rate: float = 0.06  # daily exponential decay of CTR after fatigue_start


SPECS: list[AdSpec] = [
    # Meta - prospecting
    AdSpec("meta", "SYN | Prospecting | Broad", "Broad 18-45", "UGC_Testimonial_V1", 60000, 9.0, 0.019, 0.032, 62),
    AdSpec("meta", "SYN | Prospecting | Broad", "Broad 18-45", "UGC_Testimonial_V2", 58000, 9.2, 0.0185, 0.031, 62),
    AdSpec("meta", "SYN | Prospecting | Broad", "Broad 18-45", "Static_Discount_Banner", 40000, 11.5, 0.008, 0.014, 62),
    AdSpec("meta", "SYN | Prospecting | Lookalike", "LAL 1% Buyers", "Founder_Story_Video", 45000, 10.0, 0.021, 0.030, 62,
           fatigue_start=9, fatigue_rate=0.07),
    AdSpec("meta", "SYN | Prospecting | Lookalike", "LAL 1% Buyers", "Carousel_Bestsellers", 35000, 10.5, 0.012, 0.022, 62),
    # Meta - retargeting
    AdSpec("meta", "SYN | Retargeting | 30d Visitors", "Visitors 30d", "DPA_Catalog", 18000, 14.0, 0.032, 0.060, 62,
           fatigue_start=14, fatigue_rate=0.05),
    # Google
    AdSpec("google", "SYN | Search | Brand", "Brand Exact", "RSA_Brand_1", 9000, 22.0, 0.095, 0.085, 70),
    AdSpec("google", "SYN | Shopping | All Products", "PMax Feed", "Feed_Main", 52000, 8.5, 0.014, 0.026, 66),
    AdSpec("google", "SYN | Search | Generic", "Generic Broad", "RSA_Generic_1", 30000, 19.0, 0.022, 0.010, 66),
    AdSpec("google", "SYN | Search | Generic", "Generic Broad", "RSA_Generic_2", 28000, 19.5, 0.0215, 0.0105, 66),
    # TikTok
    AdSpec("tiktok", "SYN | TikTok | Spark Ads", "Interest - Beauty", "Hook_ASMR_Unboxing", 90000, 5.5, 0.017, 0.016, 58,
           fatigue_start=7, fatigue_rate=0.08),
    AdSpec("tiktok", "SYN | TikTok | Spark Ads", "Interest - Beauty", "Hook_Problem_Solution", 80000, 5.6, 0.020, 0.022, 58),
    AdSpec("tiktok", "SYN | TikTok | Spark Ads", "Broad", "Creator_Duet_Trend", 70000, 5.0, 0.009, 0.006, 58),
    AdSpec("tiktok", "SYN | TikTok | Spark Ads", "Broad", "Static_Promo", 40000, 6.0, 0.006, 0.004, 58),
]


def generate(seed: int = 42) -> pd.DataFrame:
    """Return the unified-schema synthetic dataset."""
    rng = np.random.default_rng(seed)
    rows = []
    for spec in SPECS:
        cum_impr = 0.0
        reach_pool = spec.impr_per_day * 9.0  # audience size controls frequency growth
        for d in range(DAYS):
            day = START + pd.Timedelta(days=d)
            weekday_boost = 1.1 if day.weekday() >= 5 else 1.0
            impr = max(int(rng.normal(spec.impr_per_day, spec.impr_per_day * 0.06) * weekday_boost), 100)
            ctr = spec.ctr
            cvr = spec.cvr
            if spec.fatigue_start is not None and d >= spec.fatigue_start:
                k = d - spec.fatigue_start
                ctr *= float(np.exp(-spec.fatigue_rate * k))
                cvr *= float(np.exp(-spec.fatigue_rate * k * 0.3))
            cum_impr += impr
            if spec.fatigue_start is not None:
                freq = 1.1 + 3.4 * (cum_impr / (spec.impr_per_day * DAYS)) ** 1.1
            else:
                freq = 1.1 + 0.7 * (cum_impr / reach_pool / 3)
            freq += float(rng.normal(0, 0.03))
            clicks = int(rng.binomial(impr, min(ctr, 0.5)))
            purchases = int(rng.binomial(clicks, min(cvr, 0.9))) if clicks else 0
            cpm = spec.cpm * float(rng.normal(1.0, 0.04))
            spend = impr * cpm / 1000.0
            revenue = purchases * spec.aov * float(rng.normal(1.0, 0.05)) if purchases else 0.0
            rows.append({
                "date": day, "platform": spec.platform, "campaign": spec.campaign, "adset": spec.adset,
                "ad": spec.ad, "spend": round(spend, 2), "impressions": impr, "clicks": clicks,
                "purchases": purchases, "revenue": round(revenue, 2),
                "frequency": round(freq, 2) if spec.platform != "google" else np.nan,
            })
    return pd.DataFrame(rows)


def write_platform_exports(df: pd.DataFrame, out_dir: str | Path) -> list[Path]:
    """Write the dataset as three platform-style exports plus a combined unified sample.csv."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []

    m = df[df.platform == "meta"]
    meta = pd.DataFrame({
        "Day": m.date.dt.strftime("%Y-%m-%d"), "Campaign name": m.campaign, "Ad set name": m.adset,
        "Ad name": m.ad, "Amount spent (USD)": m.spend, "Impressions": m.impressions,
        "Link clicks": m.clicks, "Purchases": m.purchases, "Purchase conversion value": m.revenue,
        "Frequency": m.frequency,
    })
    p = out / "synthetic_meta_ads_export.csv"
    meta.to_csv(p, index=False)
    paths.append(p)

    g = df[df.platform == "google"]
    google = pd.DataFrame({
        "Day": g.date.dt.strftime("%Y-%m-%d"), "Campaign": g.campaign, "Ad group": g.adset, "Ad": g.ad,
        "Cost": g.spend, "Impr.": g.impressions.map("{:,}".format), "Clicks": g.clicks,
        "Conversions": g.purchases, "Conv. value": g.revenue,
    })
    p = out / "synthetic_google_ads_export.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write("Ad performance report (SYNTHETIC)\n")
        fh.write('"March 3, 2025 - March 30, 2025"\n')
        google.to_csv(fh, index=False)
        fh.write(f"Total: --,,,,{g.spend.sum():.2f},,,,\n")
    paths.append(p)

    t = df[df.platform == "tiktok"]
    tiktok = pd.DataFrame({
        "Date": t.date.dt.strftime("%Y-%m-%d"), "Campaign Name": t.campaign, "Ad Group Name": t.adset,
        "Ad Name": t.ad, "Cost": t.spend, "Impressions": t.impressions, "Clicks (Destination)": t.clicks,
        "Complete Payment": t.purchases, "Total Complete Payment Value": t.revenue, "Frequency": t.frequency,
    })
    p = out / "synthetic_tiktok_ads_export.csv"
    tiktok.to_csv(p, index=False)
    paths.append(p)

    p = out / "sample.csv"
    df.assign(date=df.date.dt.strftime("%Y-%m-%d")).to_csv(p, index=False)
    paths.append(p)
    return paths
