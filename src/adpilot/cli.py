"""adpilot command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import synthetic
from .agent import analyze
from .ingest import load_many


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="adpilot", description="AI media-buyer agent (recommends only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="Analyse one or more ads CSV exports")
    a.add_argument("csv", nargs="+", help="Meta / Google / TikTok export(s) or a unified-schema CSV")
    a.add_argument("--margin", type=float, required=True, help="Gross margin as a fraction, e.g. 0.35")
    a.add_argument("--product", default="your product", help="Product description for hook generation")
    a.add_argument("--out", help="Write the markdown report here (default: stdout)")
    a.add_argument("--offline", action="store_true", help="Force the deterministic offline planner")

    s = sub.add_parser("sample", help="Generate the SYNTHETIC sample data")
    s.add_argument("--out-dir", default="examples")
    s.add_argument("--seed", type=int, default=42)

    w = sub.add_parser("serve", help="Run the dashboard (FastAPI)")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)

    args = p.parse_args(argv)

    if args.cmd == "sample":
        paths = synthetic.write_platform_exports(synthetic.generate(args.seed), args.out_dir)
        for path in paths:
            print(f"wrote {path}")
        print("NOTE: all data is SYNTHETIC.")
        return 0

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("adpilot.web:app", host=args.host, port=args.port)
        return 0

    try:
        df = load_many(args.csv)
        result = analyze(df, args.margin, product=args.product, offline=args.offline)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).write_text(result.report, encoding="utf-8")
        print(f"report written to {args.out} (mode: {result.mode}, {len(result.trace)} tool calls)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(result.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
