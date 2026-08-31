#!/usr/bin/env python3
"""Compare default VO cash with a dividend-reinvested SGOV cash sleeve."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests import (
    build_target_weights,
    load_assets,
    load_market_data,
    run_portfolio_strategy,
    run_weight_strategy,
    summarize,
    toss_us_stock_fee,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--zero-fee", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "vo-sgov")
    return parser.parse_args()


def yearly_returns(equity: pd.Series, initial_cash: float) -> dict[int, float]:
    year_ends = equity.groupby(equity.index.year).last()
    prior = pd.concat([pd.Series([initial_cash]), year_ends.iloc[:-1]], ignore_index=True)
    return {int(year): float(value / base - 1.0) for (year, value), base in zip(year_ends.items(), prior)}


def main() -> int:
    args = parse_args()
    data = load_market_data(ROOT)
    sgov = load_assets(("SGOV",), ROOT)["SGOV"]
    tqqq, vo_weights = build_target_weights("vo", data)
    common = data.index.intersection(sgov.index)
    if args.end is not None:
        common = common[common <= pd.Timestamp(args.end)]
    if common.empty:
        raise ValueError("TQQQ and SGOV have no common observations")

    start, end = common[0], common[-1]
    fee_calculator = None if args.zero_fee else toss_us_stock_fee
    fee_rate = 0.0
    cash_result = run_weight_strategy(
        tqqq,
        vo_weights,
        start=start,
        end=end,
        initial_cash=args.initial_cash,
        fee_rate=fee_rate,
        fee_calculator=fee_calculator,
    )
    sleeve_weights = pd.DataFrame(
        {"TQQQ": vo_weights.loc[common], "SGOV": 1.0 - vo_weights.loc[common]},
        index=common,
    )
    sgov_result = run_portfolio_strategy(
        {"TQQQ": data.tqqq.loc[common], "SGOV": sgov.loc[common]},
        sleeve_weights,
        initial_cash=args.initial_cash,
        fee_rate=fee_rate,
        fee_calculator=fee_calculator,
    )

    rows = []
    for name, result in (("VO cash", cash_result), ("VO SGOV", sgov_result)):
        rows.append({"scenario": name, **summarize(result)})
    summary = pd.DataFrame(rows)
    yearly = pd.DataFrame(
        {
            "VO cash": yearly_returns(cash_result.equity, args.initial_cash),
            "VO SGOV": yearly_returns(sgov_result.equity, args.initial_cash),
        }
    )
    yearly.index.name = "year"
    yearly["difference"] = yearly["VO SGOV"] - yearly["VO cash"]

    args.output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output / "summary.csv", index=False, float_format="%.10f")
    yearly.to_csv(args.output / "yearly_returns.csv", float_format="%.10f")
    cash_result.equity.rename("VO cash").to_csv(
        args.output / "cash_equity.csv", float_format="%.10f"
    )
    sgov_result.equity.rename("VO SGOV").to_csv(
        args.output / "sgov_equity.csv", float_format="%.10f"
    )
    metadata = {
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "initial_cash": args.initial_cash,
        "fee_model": "zero" if args.zero_fee else "Toss Securities US stocks: 0.1%; orders <= $10 free; fee cents truncated",
        "dividend_treatment": "Yahoo Finance adjusted OHLC; distributions reinvested on ex-date",
        "asset_sha256": {
            name: hashlib.sha256((ROOT / "assets" / f"{name}.csv").read_bytes()).hexdigest()
            for name in ("TQQQ", "SGOV")
        },
    }
    (args.output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
