#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests import BATCHES, MODEL_SPECS, build_target_weights, load_market_data, run_three_percent_rule, run_vr_5, run_weight_strategy, summarize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reproducible investment-model backtests")
    parser.add_argument("--strategy", action="append", choices=sorted(MODEL_SPECS))
    parser.add_argument("--batch", choices=sorted(BATCHES))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--fee-rate", type=float, default=0.001)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = args.strategy or (list(BATCHES[args.batch]) if args.batch else None)
    if not models:
        raise SystemExit("provide --strategy or --batch")
    data = load_market_data(ROOT)
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in models:
        if model == "three_percent":
            result = run_three_percent_rule(data, start=args.start, end=args.end, initial_cash=args.initial_cash, fee_rate=args.fee_rate)
        elif model == "vr5":
            result = run_vr_5(data.tqqq.loc[data.index], start=args.start, end=args.end, initial_cash=args.initial_cash, fee_rate=args.fee_rate)
        else:
            prices, weights = build_target_weights(model, data)
            result = run_weight_strategy(prices, weights, start=args.start, end=args.end, initial_cash=args.initial_cash, fee_rate=args.fee_rate)
        model_dir = args.output / model
        model_dir.mkdir(parents=True, exist_ok=True)
        result.equity.to_csv(model_dir / "equity.csv", float_format="%.10f")
        result.trades.to_csv(model_dir / "trades.csv", float_format="%.10f")
        metrics = {"model": model, **summarize(result)}
        (model_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        rows.append(metrics)
    pd.DataFrame(rows).sort_values("cagr", ascending=False).to_csv(
        args.output / "summary.csv", index=False, float_format="%.10f"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
