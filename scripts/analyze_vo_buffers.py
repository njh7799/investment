#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests import load_market_data, run_weight_strategy, summarize
from backtests.vo_buffers import build_vo_buffer_weights


SELECTION_END = pd.Timestamp("2025-12-31")
PERIODS = {
    "full_pre2026": (None, SELECTION_END),
    "decade_2016_2025": (pd.Timestamp("2016-01-01"), SELECTION_END),
    "full_current": (None, None),
    "2026_ytd": (pd.Timestamp("2026-01-01"), None),
}
STRESS = {
    "dotcom": ("2000-03-10", "2002-10-09"),
    "global_financial_crisis": ("2007-10-31", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze preregistered VO boundary buffers")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(prices, weights, start=None, end=None, fee=0.001):
    return run_weight_strategy(prices, weights, start=start, end=end, fee_rate=fee)


def month_starts(index: pd.DatetimeIndex, years: int) -> list[pd.Timestamp]:
    eligible = index[index <= SELECTION_END - pd.DateOffset(years=years)]
    return list(pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first())


def whipsaw_row(name: str, weights: pd.Series) -> dict[str, object]:
    selected = weights.loc[:SELECTION_END]
    last_cut: int | None = None
    gaps: list[int] = []
    for location, change in enumerate(selected.diff().fillna(0.0)):
        if change < 0.0:
            last_cut = location
        elif change > 0.0 and last_cut is not None:
            gaps.append(location - last_cut)
            last_cut = None
    return {
        "model": name,
        "reductions": int((selected.diff() < 0.0).sum()),
        "increases": int((selected.diff() > 0.0).sum()),
        **{f"increases_within_{limit}": sum(gap <= limit for gap in gaps) for limit in (1, 3, 5, 10)},
    }


def bootstrap_rows(prices, weights_by_name: dict[str, pd.Series]) -> list[dict[str, object]]:
    returns = {
        name: run(prices, weights, end=SELECTION_END).equity.pct_change().fillna(0.0).to_numpy()
        for name, weights in weights_by_name.items()
    }
    observations, block, replications = len(returns["vo"]), 20, 5000
    starts = np.arange(observations - block + 1)
    block_count = (observations + block - 1) // block
    rng = np.random.default_rng(20261104)
    differences = {name: {"cagr": [], "mdd": []} for name in returns if name != "vo"}
    for begin in range(0, replications, 100):
        batch = min(100, replications - begin)
        sampled_starts = rng.choice(starts, size=(batch, block_count))
        locations = (sampled_starts[:, :, None] + np.arange(block)).reshape(batch, -1)[:, :observations]
        base_returns = returns["vo"][locations]
        base_curve = np.cumprod(1.0 + base_returns, axis=1)
        base_cagr = np.prod(1.0 + base_returns, axis=1) ** (252.0 / observations) - 1.0
        base_mdd = np.min(base_curve / np.maximum.accumulate(base_curve, axis=1) - 1.0, axis=1)
        for name in differences:
            sampled = returns[name][locations]
            curve = np.cumprod(1.0 + sampled, axis=1)
            differences[name]["cagr"].extend(np.prod(1.0 + sampled, axis=1) ** (252.0 / observations) - 1.0 - base_cagr)
            differences[name]["mdd"].extend(np.min(curve / np.maximum.accumulate(curve, axis=1) - 1.0, axis=1) - base_mdd)
    rows = []
    for name, metrics in differences.items():
        for metric, raw in metrics.items():
            values = np.asarray(raw)
            rows.append({
                "model": name,
                "metric": metric,
                "median_delta": float(np.median(values)),
                "ci95_low": float(np.quantile(values, 0.025)),
                "ci95_high": float(np.quantile(values, 0.975)),
                "probability_positive": float(np.mean(values > 0.0)),
            })
    return rows


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    prices, weights_by_name, specs = build_vo_buffer_weights(data)
    pd.DataFrame([spec.__dict__ for spec in specs]).to_csv(args.output / "variants.csv", index=False)

    period_rows = []
    for period_name, (start, end) in PERIODS.items():
        for name, weights in weights_by_name.items():
            period_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights, start, end))})
    period = pd.DataFrame(period_rows)
    period.to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    whipsaw = pd.DataFrame([whipsaw_row(name, weights) for name, weights in weights_by_name.items()])
    whipsaw.to_csv(args.output / "whipsaw-summary.csv", index=False)

    rolling_rows = []
    for years in (5, 10):
        starts = month_starts(prices.index, years)
        for name, weights in weights_by_name.items():
            metrics = [summarize(run(prices, weights, start, min(start + pd.DateOffset(years=years), SELECTION_END))) for start in starts]
            rolling_rows.append({
                "model": name,
                "window_years": years,
                "window_count": len(metrics),
                "median_cagr": float(np.median([item["cagr"] for item in metrics])),
                "worst_cagr": float(min(item["cagr"] for item in metrics)),
                "median_mdd": float(np.median([item["mdd"] for item in metrics])),
                "worst_mdd": float(min(item["mdd"] for item in metrics)),
            })
    pd.DataFrame(rolling_rows).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    stress_rows = []
    for period_name, (start, end) in STRESS.items():
        for name, weights in weights_by_name.items():
            stress_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights, start, end))})
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in (0.001, 0.002, 0.005):
        for period_name, start in (("full_pre2026", None), ("decade_2016_2025", pd.Timestamp("2016-01-01"))):
            for name, weights in weights_by_name.items():
                fee_rows.append({"fee_rate": fee, "period": period_name, "model": name, **summarize(run(prices, weights, start, SELECTION_END, fee))})
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    pd.DataFrame(bootstrap_rows(prices, weights_by_name)).to_csv(args.output / "bootstrap-summary.csv", index=False, float_format="%.10f")

    full = period[period.period == "full_pre2026"].set_index("model")
    baseline = full.loc["vo"]
    quick_base = int(whipsaw.set_index("model").loc["vo", "increases_within_5"])
    screen_rows = []
    for name in weights_by_name:
        if name == "vo":
            continue
        row = full.loc[name]
        quick = int(whipsaw.set_index("model").loc[name, "increases_within_5"])
        screen_rows.append({
            "model": name,
            "cagr_delta": float(row.cagr - baseline.cagr),
            "mdd_delta": float(row.mdd - baseline.mdd),
            "annual_trades_delta": float(row.annual_trades - baseline.annual_trades),
            "quick_increase_reduction": float(1.0 - quick / quick_base),
            "practical_screen": bool(
                row.cagr - baseline.cagr >= -0.005
                and row.mdd - baseline.mdd >= -0.02
                and quick <= quick_base * 0.75
                and row.annual_trades <= baseline.annual_trades
            ),
            "meaningful_effect": bool(
                (row.cagr - baseline.cagr >= 0.005 and row.mdd - baseline.mdd >= -0.01)
                or (row.mdd - baseline.mdd >= 0.03 and row.cagr - baseline.cagr >= -0.005)
            ),
        })
    pd.DataFrame(screen_rows).to_csv(args.output / "screening-summary.csv", index=False, float_format="%.10f")

    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "selection_data_end": SELECTION_END.date().isoformat(),
        "preregistration": "docs/research/preregistrations/batch-12-vo-boundary-buffers.yaml",
        "preregistered_commit": "7c85b7d",
        "variant_count": len(specs),
        "initial_cash": 100000,
        "base_fee_rate": 0.001,
        "bootstrap": {"block_sessions": 20, "replications": 5000, "seed": 20261104},
        "asset_sha256": {"TQQQ.csv": hashlib.sha256((ROOT / "assets/TQQQ.csv").read_bytes()).hexdigest()},
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
