"""Parse ads-platform CSV exports and normalise them to one schema."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA = [
    "date", "platform", "campaign", "adset", "ad",
    "spend", "impressions", "clicks", "purchases", "revenue", "frequency",
]
NUMERIC = ["spend", "impressions", "clicks", "purchases", "revenue", "frequency"]

# Aliases are compared after normalisation (lowercase, non-alphanumerics -> single space).
ALIASES: dict[str, list[str]] = {
    "date": ["date", "day", "reporting starts", "stat time day", "stat time", "segments date"],
    "campaign": ["campaign", "campaign name"],
    "adset": ["adset", "ad set name", "ad set", "ad group", "ad group name", "adgroup name"],
    "ad": ["ad", "ad name"],
    "spend": ["spend", "amount spent", "amount spent usd", "amount spent eur", "cost", "total cost"],
    "impressions": ["impressions", "impr"],
    "clicks": ["clicks", "link clicks", "clicks all", "clicks destination"],
    "purchases": ["purchases", "website purchases", "results", "conversions", "complete payment",
                  "total complete payment"],
    "revenue": ["revenue", "purchase conversion value", "website purchases conversion value",
                "conv value", "conversion value", "total complete payment value",
                "complete payment value"],
    "frequency": ["frequency", "avg frequency"],
}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(h).lower()).strip()


_LOOKUP = {_norm(a): canon for canon, al in ALIASES.items() for a in al}


def detect_platform(columns: list[str]) -> str:
    """Guess the platform from header style."""
    n = {_norm(c) for c in columns}
    if n & {"ad set name", "amount spent usd", "amount spent", "link clicks", "reporting starts"}:
        return "meta"
    if n & {"impr", "conv value", "ad group"}:
        return "google"
    if n & {"ad group name", "stat time day", "total complete payment value"}:
        return "tiktok"
    return "unknown"


def _to_number(s: pd.Series) -> pd.Series:
    if s.dtype.kind in "if":
        return s.astype(float)
    cleaned = (
        s.astype(str)
        .str.replace(r"[^0-9.,\-]", "", regex=True)
        .str.replace(",", "", regex=False)
        .replace({"": np.nan, "-": np.nan, "--": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalise(df: pd.DataFrame, platform: str | None = None) -> pd.DataFrame:
    """Map raw export columns onto the unified schema."""
    platform = platform or detect_platform(list(df.columns))
    rename: dict[str, str] = {}
    for col in df.columns:
        canon = _LOOKUP.get(_norm(col))
        if canon and canon not in rename.values():
            rename[col] = canon
    out = df.rename(columns=rename).copy()
    if "platform" not in out.columns:
        out["platform"] = platform
    required = ("date", "campaign", "spend", "impressions", "clicks")
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"Could not map required columns {missing}. Found headers: {list(df.columns)}")
    for c in ("adset", "ad"):
        if c not in out.columns:
            out[c] = "(all)"
    for c in ("purchases", "revenue"):
        if c not in out.columns:
            out[c] = 0.0
    if "frequency" not in out.columns:
        out["frequency"] = np.nan
    for c in NUMERIC:
        out[c] = _to_number(out[c])
    base = ["spend", "impressions", "clicks", "purchases", "revenue"]
    out[base] = out[base].fillna(0.0)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["platform"] = out["platform"].astype(str).str.lower()
    for c in ("campaign", "adset", "ad"):
        out[c] = out[c].astype(str).str.strip()
    return out[SCHEMA].sort_values(["date", "platform", "campaign", "adset", "ad"]).reset_index(drop=True)


def load_csv(path: str | Path, platform: str | None = None) -> pd.DataFrame:
    """Load one export. Skips title rows (Google Ads) and trailing 'Total' rows."""
    path = Path(path)
    with open(path, encoding="utf-8-sig") as fh:
        lines = fh.readlines()
    skip = 0
    for i, line in enumerate(lines[:10]):
        if "campaign" in line.lower() and "," in line:
            skip = i
            break
    df = pd.read_csv(path, skiprows=skip, encoding="utf-8-sig")
    first = df.columns[0]
    df = df[~df[first].astype(str).str.lower().str.startswith("total")]
    return normalise(df, platform)


def load_many(paths: list[str | Path]) -> pd.DataFrame:
    frames = [load_csv(p) for p in paths]
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["date", "platform", "campaign", "adset", "ad"])
        .reset_index(drop=True)
    )
