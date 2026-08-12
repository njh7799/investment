#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests import build_target_weights, load_assets, load_market_data, run_portfolio_strategy, run_weight_strategy, summarize
from backtests.allocation_models import ERC8_ASSETS, build_allocation_weights

MODELS = ("erc8_equal_monthly", "erc8", "tqqq_hold", "qqq_hold", "vo")
PERIODS = {"common_full": (None, None), "recent_10y": ("2016-08-01", None)}
STRESS = {
    "global_financial_crisis_available": (None, "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze preregistered ERC 8-ETF adaptation")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


@lru_cache(maxsize=1)
def prepared():
    assets = load_assets(ERC8_ASSETS, ROOT)
    index = next(iter(assets.values())).index
    for frame in list(assets.values())[1:]:
        index = index.intersection(frame.index)
    closes = pd.DataFrame({name: assets[name].loc[index, "Close"] for name in ERC8_ASSETS}, index=index)
    targets = {model: build_allocation_weights(model, closes) for model in ("erc8_equal_monthly", "erc8")}
    first_signal = targets["erc8"].sum(axis=1).ne(0.0).idxmax()
    evaluation_start = index[index.get_loc(first_signal) + 1]
    return assets, targets, evaluation_start


@lru_cache(maxsize=1)
def market():
    return load_market_data(ROOT)


def evaluation_start() -> pd.Timestamp:
    return prepared()[2]


@lru_cache(maxsize=None)
def weights(model: str):
    if model in {"tqqq_hold", "qqq_hold", "vo"}:
        return build_target_weights(model, market())
    assets, targets, _ = prepared()
    return assets, targets[model]


def run(model: str, start=None, end=None, fee=0.001):
    prices, target = weights(model)
    actual_start = start or evaluation_start()
    if model in {"tqqq_hold", "qqq_hold", "vo"}:
        return run_weight_strategy(prices, target, start=actual_start, end=end, fee_rate=fee)
    return run_portfolio_strategy(prices, target, start=actual_start, end=end, fee_rate=fee, rebalance_monthly=True)


def rolling_rows(years: int) -> list[dict[str, object]]:
    index = market().index
    eligible = index[(index >= evaluation_start()) & (index <= index[-1] - pd.DateOffset(years=years))]
    starts = list(pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first())
    rows = []
    for model in MODELS:
        metrics = [summarize(run(model, start, min(start + pd.DateOffset(years=years), index[-1]))) for start in starts]
        rows.append({
            "model": model,
            "window_years": years,
            "window_count": len(metrics),
            "median_cagr": float(pd.Series([item["cagr"] for item in metrics]).median()),
            "worst_cagr": float(min(item["cagr"] for item in metrics)),
            "median_mdd": float(pd.Series([item["mdd"] for item in metrics]).median()),
            "worst_mdd": float(min(item["mdd"] for item in metrics)),
            "median_longest_tuw_days": float(pd.Series([item["longest_time_underwater_days"] for item in metrics]).median()),
            "worst_longest_tuw_days": int(max(item["longest_time_underwater_days"] for item in metrics)),
        })
    return rows


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    period_rows = [{"period": period, "model": model, **summarize(run(model, start, end))} for period, (start, end) in PERIODS.items() for model in MODELS]
    pd.DataFrame(period_rows).to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")
    stress_rows = [{"period": period, "model": model, **summarize(run(model, start, end))} for period, (start, end) in STRESS.items() for model in MODELS]
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")
    pd.DataFrame(rolling_rows(5) + rolling_rows(10)).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")
    fee_rows = [{"fee_rate": fee, "model": model, **summarize(run(model, fee=fee))} for fee in (0.001, 0.002, 0.005) for model in MODELS]
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")
    metadata = {
        "generated_through": market().index[-1].date().isoformat(),
        "common_start": evaluation_start().date().isoformat(),
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "models": list(MODELS),
        "preregistration": "docs/research/preregistrations/batch-09-erc8.yaml",
        "asset_sha256": {name: hashlib.sha256((ROOT / "assets" / f"{name}.csv").read_bytes()).hexdigest() for name in ERC8_ASSETS},
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
