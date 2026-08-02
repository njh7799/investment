#!/usr/bin/env python3
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

from backtests import BATCHES, MODEL_SPECS, build_target_weights, load_market_data, run_three_percent_rule, run_vr_5, run_weight_strategy, summarize


ACTUAL_START = pd.Timestamp("2010-02-11")
PERIODS = {
    "full_synthetic": (None, None),
    "actual_tqqq": ("2010-02-11", None),
    "recent_10y": ("2016-07-31", None),
}
STRESS = {
    "dotcom": ("2000-03-10", "2002-10-09"),
    "global_financial_crisis": ("2007-10-31", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a preregistered model batch")
    parser.add_argument("--batch", choices=sorted(BATCHES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(model, data, start=None, end=None, fee=0.001):
    if model == "three_percent":
        return run_three_percent_rule(data, start=start, end=end, fee_rate=fee)
    if model == "vr5":
        return run_vr_5(data.tqqq.loc[data.index], start=start, end=end, fee_rate=fee)
    prices, weights = build_target_weights(model, data)
    return run_weight_strategy(prices, weights, start=start, end=end, fee_rate=fee)


def month_starts(index: pd.DatetimeIndex, start: pd.Timestamp, last: pd.Timestamp) -> list[pd.Timestamp]:
    eligible = index[(index >= start) & (index <= last)]
    series = pd.Series(eligible, index=eligible)
    return list(series.groupby(eligible.to_period("M")).first())


def rolling_rows(data, models: tuple[str, ...], years: int) -> list[dict[str, object]]:
    index = data.index
    starts = month_starts(index, ACTUAL_START, index[-1] - pd.DateOffset(years=years))
    rows = []
    for model in models:
        values = []
        mdds = []
        tuws = []
        for start in starts:
            end = min(start + pd.DateOffset(years=years), index[-1])
            metrics = summarize(run(model, data, start=start, end=end))
            values.append(metrics["cagr"])
            mdds.append(metrics["mdd"])
            tuws.append(metrics["longest_time_underwater_days"])
        rows.append(
            {
                "model": model,
                "window_years": years,
                "window_count": len(values),
                "median_cagr": float(pd.Series(values).median()),
                "worst_cagr": float(min(values)),
                "median_mdd": float(pd.Series(mdds).median()),
                "worst_mdd": float(min(mdds)),
                "median_longest_tuw_days": float(pd.Series(tuws).median()),
                "worst_longest_tuw_days": int(max(tuws)),
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    models = BATCHES[args.batch]

    period_rows = []
    for period, (start, end) in PERIODS.items():
        for model in models:
            period_rows.append({"period": period, "model": model, **summarize(run(model, data, start, end))})
    pd.DataFrame(period_rows).to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    stress_rows = []
    for period, (start, end) in STRESS.items():
        for model in models:
            stress_rows.append({"period": period, "model": model, **summarize(run(model, data, start, end))})
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    rolling = rolling_rows(data, models, 5) + rolling_rows(data, models, 10)
    pd.DataFrame(rolling).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in [0.001, 0.002, 0.005]:
        for model in models:
            fee_rows.append({"fee_rate": fee, "model": model, **summarize(run(model, data, ACTUAL_START, fee=fee))})
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    hashes = {}
    for name in ["IXIC.csv", "QQQ.csv", "TQQQ.csv"]:
        hashes[name] = hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "actual_tqqq_start": ACTUAL_START.date().isoformat(),
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "batch": args.batch,
        "models": list(models),
        "asset_sha256": hashes,
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
