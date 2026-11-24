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

from backtests import build_target_weights, load_market_data, run_weight_strategy, summarize
from backtests.fixed_allocation import run_fixed_allocation


CALENDAR = ("daily", "weekly", "monthly", "quarterly", "annual", "never")
BANDS = (0.05, 0.10, 0.20)
FEES = (0.0, 0.001, 0.002, 0.005)
STRESS = {
    "dotcom_bust": ("2000-03-24", "2002-10-09"),
    "global_financial_crisis": ("2007-10-09", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze preregistered fixed TQQQ/QQQ/cash allocations")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def weight_grid(step: int) -> list[tuple[float, float, float]]:
    units = 100 // step
    return [(a / units, b / units, (units - a - b) / units)
            for a in range(units + 1) for b in range(units - a + 1)]


def policies() -> list[tuple[str, str | float]]:
    return [(f"calendar_{name}", name) for name in CALENDAR] + [
        (f"band_{int(band * 100):02d}pp", band) for band in BANDS
    ]


def target_name(target: tuple[float, float, float]) -> str:
    return "t%03d_q%03d_c%03d" % tuple(round(weight * 100) for weight in target)


def model_fields(target: tuple[float, float, float], policy_name: str) -> dict[str, object]:
    return {
        "model": f"{target_name(target)}__{policy_name}",
        "policy": policy_name,
        "tqqq_weight": target[0],
        "qqq_weight": target[1],
        "cash_weight": target[2],
        "nominal_exposure": 3 * target[0] + target[1],
    }


def metric_row(diagnostics) -> dict[str, object]:
    result = diagnostics.result
    metrics = summarize(result)
    metrics["scheduled_reviews"] = diagnostics.scheduled_reviews
    metrics["turnover"] = diagnostics.turnover
    metrics["turnover_multiple_initial"] = diagnostics.turnover / result.initial_cash
    return metrics


def rolling_slice_metrics(equity: pd.Series, start: pd.Timestamp, years: int) -> dict[str, float] | None:
    end = start + pd.DateOffset(years=years)
    window = equity.loc[start:end]
    if len(window) < 2 or window.index[-1] < end - pd.Timedelta(days=7):
        return None
    values = window.to_numpy(float)
    dates = window.index.to_numpy(dtype="datetime64[D]")
    elapsed = float((window.index[-1] - window.index[0]).days / 365.2425)
    running = np.maximum.accumulate(values)
    mdd = float(np.min(values / running - 1.0))
    high = values >= running * (1.0 - 1e-12)
    high_locations = np.flatnonzero(high)
    boundaries = np.concatenate(([0], high_locations, [len(values) - 1]))
    longest = int(np.max(np.diff(dates[boundaries]).astype("timedelta64[D]").astype(int)))
    return {
        "cagr": float((values[-1] / values[0]) ** (1.0 / elapsed) - 1.0),
        "mdd": mdd,
        "longest_tuw_days": longest,
    }


def rolling_summary(equity: pd.Series, years: int) -> dict[str, object]:
    eligible = equity.index[equity.index <= equity.index[-1] - pd.DateOffset(years=years)]
    starts = pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first().tolist()
    rows = [row for start in starts if (row := rolling_slice_metrics(equity, start, years))]
    return {
        "window_years": years,
        "window_count": len(rows),
        "median_cagr": float(np.median([row["cagr"] for row in rows])),
        "worst_cagr": float(min(row["cagr"] for row in rows)),
        "median_mdd": float(np.median([row["mdd"] for row in rows])),
        "worst_mdd": float(min(row["mdd"] for row in rows)),
        "median_longest_tuw_days": float(np.median([row["longest_tuw_days"] for row in rows])),
        "worst_longest_tuw_days": int(max(row["longest_tuw_days"] for row in rows)),
    }


def pareto_flags(frame: pd.DataFrame) -> pd.Series:
    values = frame[["cagr", "mdd", "longest_time_underwater_days"]].to_numpy(float)
    keep = np.ones(len(values), dtype=bool)
    for location, candidate in enumerate(values):
        dominates = (
            (values[:, 0] >= candidate[0])
            & (values[:, 1] >= candidate[1])
            & (values[:, 2] <= candidate[2])
            & ((values[:, 0] > candidate[0]) | (values[:, 1] > candidate[1]) | (values[:, 2] < candidate[2]))
        )
        keep[location] = not bool(np.any(dominates))
    return pd.Series(keep, index=frame.index)


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    index = data.qqq.index.intersection(data.tqqq.index)
    end = index[-1]
    fixed_periods = {
        "synthetic_full": ("1999-03-10", None),
        "first_decade": ("1999-03-10", "2009-03-09"),
        "second_decade": ("2009-03-10", "2019-03-09"),
        "latest_segment": ("2019-03-10", None),
        "recent_10y_auxiliary": ((end - pd.DateOffset(years=10)).date().isoformat(), None),
    }

    def run(target: tuple[float, float, float], policy_name: str, policy_value: str | float,
            fee: float = 0.001, start: str | None = None, finish: str | None = None):
        kwargs = {"frequency": policy_value} if isinstance(policy_value, str) else {"band": policy_value}
        return run_fixed_allocation(data.tqqq, data.qqq, target, fee_rate=fee,
                                    start=start, end=finish, record_positions=False,
                                    record_trade_details=False, **kwargs)

    primary_rows: list[dict[str, object]] = []
    rolling_rows: list[dict[str, object]] = []
    for target in weight_grid(10):
        for policy_name, policy_value in policies():
            diagnostics = run(target, policy_name, policy_value)
            fields = model_fields(target, policy_name)
            primary_rows.append({**fields, **metric_row(diagnostics)})
            for years in (5, 10):
                rolling_rows.append({**fields, **rolling_summary(diagnostics.result.equity, years)})
    primary = pd.DataFrame(primary_rows)
    primary["pareto_combined"] = pareto_flags(primary)
    primary["pareto_within_policy"] = primary.groupby("policy", group_keys=False).apply(
        lambda group: pareto_flags(group), include_groups=False
    ).sort_index()
    primary.to_csv(args.output / "primary-full-summary.csv", index=False, float_format="%.10f")
    pd.DataFrame(rolling_rows).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    stability_rows = []
    for target in weight_grid(5):
        for policy_name, policy_value in policies():
            diagnostics = run(target, policy_name, policy_value)
            stability_rows.append({**model_fields(target, policy_name), **metric_row(diagnostics)})
    pd.DataFrame(stability_rows).to_csv(
        args.output / "stability-5pp-full-summary.csv", index=False, float_format="%.10f"
    )

    period_rows = []
    for period, (start, finish) in fixed_periods.items():
        for target in weight_grid(10):
            for policy_name, policy_value in policies():
                period_rows.append({"period": period, **model_fields(target, policy_name),
                                    **metric_row(run(target, policy_name, policy_value, start=start, finish=finish))})
    pd.DataFrame(period_rows).to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    stress_rows = []
    for period, (start, finish) in STRESS.items():
        for target in weight_grid(10):
            for policy_name, policy_value in policies():
                stress_rows.append({"period": period, **model_fields(target, policy_name),
                                    **metric_row(run(target, policy_name, policy_value, start=start, finish=finish))})
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in FEES:
        for target in weight_grid(10):
            for policy_name, policy_value in policies():
                fee_rows.append({"fee_rate": fee, **model_fields(target, policy_name),
                                 **metric_row(run(target, policy_name, policy_value, fee=fee))})
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    benchmark_rows = []
    for model in ("tqqq_hold", "qqq_hold", "vo"):
        prices, weights = build_target_weights(model, data)
        result = run_weight_strategy(prices, weights, start="1999-03-10", fee_rate=0.001)
        benchmark_rows.append({"model": model, **summarize(result)})
    pd.DataFrame(benchmark_rows).to_csv(args.output / "integration-benchmarks.csv", index=False, float_format="%.10f")

    anchors = {
        "tqqq_cash_one_third": (1 / 3, 0.0, 2 / 3),
        "tqqq_cash_half": (0.5, 0.0, 0.5),
        "tqqq_cash_two_thirds": (2 / 3, 0.0, 1 / 3),
        "tqqq_qqq_half": (0.5, 0.5, 0.0),
        "equal_three_way": (1 / 3, 1 / 3, 1 / 3),
    }
    anchor_rows = []
    for anchor, target in anchors.items():
        for policy_name, policy_value in policies():
            anchor_rows.append({"anchor": anchor, **model_fields(target, policy_name),
                                **metric_row(run(target, policy_name, policy_value))})
    pd.DataFrame(anchor_rows).to_csv(args.output / "anchor-summary.csv", index=False, float_format="%.10f")

    metadata = {
        "preregistration_commit": "d107409",
        "generated_through": end.date().isoformat(),
        "initial_cash": 100_000,
        "base_fee_rate_each_side": 0.001,
        "cash_return": 0,
        "primary_targets": len(weight_grid(10)),
        "stability_targets": len(weight_grid(5)),
        "policies": [name for name, _ in policies()],
        "rolling_start_cadence": "first common trading session of every calendar month; windows use the continuous full-history policy path",
        "asset_sha256": {
            name: hashlib.sha256((ROOT / "assets" / f"{name}.csv").read_bytes()).hexdigest()
            for name in ("TQQQ", "QQQ")
        },
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
