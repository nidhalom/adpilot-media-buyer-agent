"""FastAPI dashboard: upload CSV (or use the synthetic sample) -> charts + report."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import synthetic, tools
from .agent import analyze
from .ingest import detect_platform, normalise

app = FastAPI(title="AdPilot", description="AI media-buyer agent. Recommends only.")
STATIC = Path(__file__).parent / "static"


def build_payload(df: pd.DataFrame, margin: float, offline: bool = True, product: str = "your product") -> dict:
    be = tools.breakeven_roas(margin)
    ads = tools.compute_kpis(df, ["platform", "campaign", "adset", "ad"])
    fatigue = tools.detect_creative_fatigue(df)
    result = analyze(df, margin, product=product, offline=offline)
    return {
        "breakeven_roas": be,
        "mode": result.mode,
        "overall": tools.compute_kpis(df)[0],
        "ads": [{k: (None if isinstance(v, float) and v != v else v) for k, v in a.items()
                 if k in ("ad", "platform", "spend", "roas", "cpa", "ctr", "purchases")} for a in ads],
        "fatigue": [f for f in fatigue if f["status"] != "healthy"][:6],
        "report_md": result.report,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/sample")
def sample(margin: float = 0.35) -> dict:
    return build_payload(synthetic.generate(), margin)


@app.post("/api/analyze")
async def analyze_csv(request: Request, margin: float = 0.35, offline: bool = True) -> dict:
    """Body: raw CSV text (one platform export or unified schema)."""
    raw = (await request.body()).decode("utf-8-sig", errors="replace")
    try:
        df = pd.read_csv(io.StringIO(raw))
        df = normalise(df, detect_platform(list(df.columns)))
        return build_payload(df, margin, offline)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
