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
from backtests.allocation_models import ALLOCATION_MODELS, build_allocation_weights


PERIODS = {"common_full": (None, None), "recent_10y": ("2016-07-31", None)}
MODELS = ("tqqq_hold", "qqq_hold", "vo", *ALLOCATION_MODELS)
COMMON_START = "2007-03-08"
STRESS = {
    "global_financial_crisis": ("2007-10-31", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze preregistered multi-asset allocation models")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


@lru_cache(maxsize=1)
def market_data():
    return load_market_data(ROOT)


@lru_cache(maxsize=None)
def prepared_benchmark(model: str):
    return build_target_weights(model, market_data())


@lru_cache(maxsize=None)
def prepared_allocation(model: str):
    names = ALLOCATION_MODELS[model]
    assets = load_assets(names, ROOT)
    index = next(iter(assets.values())).index
    for frame in list(assets.values())[1:]:
        index = index.intersection(frame.index)
    closes = pd.DataFrame({name: assets[name].loc[index, "Close"] for name in names}, index=index)
    return assets, build_allocation_weights(model, closes)


def run(model: str, start=None, end=None, fee=0.001):
    if model in {"tqqq_hold", "qqq_hold", "vo"}:
        prices, weights = prepared_benchmark(model)
        return run_weight_strategy(prices, weights, start=start or COMMON_START, end=end, fee_rate=fee)
    assets, weights = prepared_allocation(model)
    return run_portfolio_strategy(
        assets,
        weights,
        start=start or COMMON_START,
        end=end,
        fee_rate=fee,
        rebalance_monthly=model in {"gtaa5", "gem"},
    )


def rolling_rows(years: int) -> list[dict[str, object]]:
    index = load_market_data(ROOT).index
    eligible = index[(index >= pd.Timestamp(COMMON_START)) & (index <= index[-1] - pd.DateOffset(years=years))]
    starts = list(pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first())
    rows = []
    for model in MODELS:
        metrics = [summarize(run(model, start, min(start + pd.DateOffset(years=years), index[-1]))) for start in starts]
        rows.append({
            "model": model,
            "window_years": years,
            "window_count": len(metrics),
            "median_cagr": float(pd.Series([m["cagr"] for m in metrics]).median()),
            "worst_cagr": float(min(m["cagr"] for m in metrics)),
            "worst_mdd": float(min(m["mdd"] for m in metrics)),
            "worst_longest_tuw_days": int(max(m["longest_time_underwater_days"] for m in metrics)),
        })
    return rows


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for period, (start, end) in PERIODS.items():
        for model in MODELS:
            rows.append({"period": period, "model": model, **summarize(run(model, start, end))})
    pd.DataFrame(rows).to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")
    stress = []
    for period, (start, end) in STRESS.items():
        for model in MODELS:
            stress.append({"period": period, "model": model, **summarize(run(model, start, end))})
    pd.DataFrame(stress).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")
    pd.DataFrame(rolling_rows(5) + rolling_rows(10)).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")
    fee_rows = []
    for fee in (0.001, 0.002, 0.005):
        for model in MODELS:
            fee_rows.append({"fee_rate": fee, "model": model, **summarize(run(model, fee=fee))})
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")
    names = sorted({name for group in ALLOCATION_MODELS.values() for name in group})
    metadata = {
        "generated_through": min(pd.read_csv(ROOT / "assets" / f"{name}.csv").iloc[-1, 0] for name in names),
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "models": list(MODELS),
        "asset_sha256": {name: hashlib.sha256((ROOT / "assets" / f"{name}.csv").read_bytes()).hexdigest() for name in names},
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
