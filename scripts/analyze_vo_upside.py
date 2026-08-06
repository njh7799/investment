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

from backtests import load_market_data, run_weight_strategy, summarize
from backtests.vo_upside import build_vo_upside_weights


ACTUAL_START = pd.Timestamp("2010-02-11")
PRE_2026_END = pd.Timestamp("2025-12-31")
PERIODS = {
    "full_pre2026": (None, PRE_2026_END),
    "actual_pre2026": (ACTUAL_START, PRE_2026_END),
    "decade_2016_2025": (pd.Timestamp("2016-01-01"), PRE_2026_END),
    "full_current": (None, None),
    "actual_current": (ACTUAL_START, None),
    "2026_ytd": (pd.Timestamp("2026-01-01"), None),
}
STRESS = {
    "dotcom": ("2000-03-10", "2002-10-09"),
    "global_financial_crisis": ("2007-10-31", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze 30-day directional VO overrides")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(prices, weights, start=None, end=None, fee=0.001):
    return run_weight_strategy(prices, weights, start=start, end=end, fee_rate=fee)


def month_starts(index: pd.DatetimeIndex, years: int) -> list[pd.Timestamp]:
    last_start = PRE_2026_END - pd.DateOffset(years=years)
    eligible = index[(index >= ACTUAL_START) & (index <= last_start)]
    series = pd.Series(eligible, index=eligible)
    return list(series.groupby(eligible.to_period("M")).first())


def rolling_rows(prices, weights_by_name, names: list[str], years: int) -> list[dict[str, object]]:
    rows = []
    for name in names:
        cagr_values: list[float] = []
        mdd_values: list[float] = []
        tuw_values: list[int] = []
        for start in month_starts(prices.index, years):
            end = min(start + pd.DateOffset(years=years), PRE_2026_END)
            metrics = summarize(run(prices, weights_by_name[name], start=start, end=end))
            cagr_values.append(float(metrics["cagr"]))
            mdd_values.append(float(metrics["mdd"]))
            tuw_values.append(int(metrics["longest_time_underwater_days"]))
        rows.append(
            {
                "model": name,
                "window_years": years,
                "window_count": len(cagr_values),
                "median_cagr": float(pd.Series(cagr_values).median()),
                "worst_cagr": min(cagr_values),
                "median_mdd": float(pd.Series(mdd_values).median()),
                "worst_mdd": min(mdd_values),
                "median_longest_tuw_days": float(pd.Series(tuw_values).median()),
                "worst_longest_tuw_days": max(tuw_values),
            }
        )
    return rows


def select_screen(period: pd.DataFrame) -> pd.DataFrame:
    indexed = period.set_index(["period", "model"])
    baseline = {period_name: indexed.loc[(period_name, "vo")] for period_name in PERIODS}
    rows = []
    for model in period["model"].unique():
        if model == "vo":
            continue
        full = indexed.loc[("full_pre2026", model)]
        actual = indexed.loc[("actual_pre2026", model)]
        decade = indexed.loc[("decade_2016_2025", model)]
        full_base = baseline["full_pre2026"]
        actual_base = baseline["actual_pre2026"]
        decade_base = baseline["decade_2016_2025"]
        full_cagr_delta = float(full.cagr - full_base.cagr)
        actual_cagr_delta = float(actual.cagr - actual_base.cagr)
        decade_cagr_delta = float(decade.cagr - decade_base.cagr)
        full_mdd_delta = float(full.mdd - full_base.mdd)
        actual_mdd_delta = float(actual.mdd - actual_base.mdd)
        passed = (
            full_cagr_delta >= -0.005
            and actual_cagr_delta >= 0.0
            and decade_cagr_delta >= 0.0
            and full_mdd_delta >= -0.02
            and actual_mdd_delta >= -0.02
            and float(actual.annual_trades) <= 20.0
        )
        rows.append(
            {
                "model": model,
                "screen_pass": passed,
                "full_cagr_delta": full_cagr_delta,
                "actual_cagr_delta": actual_cagr_delta,
                "decade_cagr_delta": decade_cagr_delta,
                "full_mdd_delta": full_mdd_delta,
                "actual_mdd_delta": actual_mdd_delta,
                "actual_annual_trades": float(actual.annual_trades),
                "rank_floor": min(full_cagr_delta, actual_cagr_delta, decade_cagr_delta),
                "rank_sum": full_cagr_delta + actual_cagr_delta + decade_cagr_delta,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["screen_pass", "rank_floor", "rank_sum"], ascending=[False, False, False]
    )


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    prices, weights_by_name, specs = build_vo_upside_weights(data)

    variant_rows = [spec.__dict__ for spec in specs]
    pd.DataFrame(variant_rows).to_csv(args.output / "variants.csv", index=False)

    period_rows = []
    for period, (start, end) in PERIODS.items():
        for name, weights in weights_by_name.items():
            period_rows.append({"period": period, "model": name, **summarize(run(prices, weights, start, end))})
    period = pd.DataFrame(period_rows)
    period.to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    screen = select_screen(period)
    selection_mask = weights_by_name["vo"].index <= PRE_2026_END
    base_digest = hashlib.sha256(weights_by_name["vo"].loc[selection_mask].to_numpy().tobytes()).hexdigest()
    seen_paths = {base_digest: "vo"}
    duplicate_of: dict[str, str | None] = {}
    changed_days_pre2026: dict[str, int] = {}
    changed_days_current: dict[str, int] = {}
    shortlist: list[str] = []
    for model in screen["model"]:
        weights = weights_by_name[model]
        digest = hashlib.sha256(weights.loc[selection_mask].to_numpy().tobytes()).hexdigest()
        duplicate_of[model] = seen_paths.get(digest)
        changed_days_pre2026[model] = int(
            (weights.loc[selection_mask] != weights_by_name["vo"].loc[selection_mask]).sum()
        )
        changed_days_current[model] = int((weights != weights_by_name["vo"]).sum())
        if digest not in seen_paths:
            seen_paths[digest] = model
            if bool(screen.loc[screen.model == model, "screen_pass"].iloc[0]) and len(shortlist) < 20:
                shortlist.append(model)
    screen["changed_target_days_pre2026"] = screen["model"].map(changed_days_pre2026)
    screen["changed_target_days_current"] = screen["model"].map(changed_days_current)
    screen["duplicate_of"] = screen["model"].map(duplicate_of)
    screen.to_csv(args.output / "screening-summary.csv", index=False, float_format="%.10f")
    evaluated = ["vo", *shortlist]

    stress_rows = []
    for period_name, (start, end) in STRESS.items():
        for name in evaluated:
            stress_rows.append(
                {"period": period_name, "model": name, **summarize(run(prices, weights_by_name[name], start, end))}
            )
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    annual_rows = []
    for year in range(2010, 2026):
        for name in evaluated:
            annual_rows.append(
                {
                    "year": year,
                    "model": name,
                    **summarize(run(prices, weights_by_name[name], f"{year}-01-01", f"{year}-12-31")),
                }
            )
    pd.DataFrame(annual_rows).to_csv(args.output / "annual-summary.csv", index=False, float_format="%.10f")

    rolling = rolling_rows(prices, weights_by_name, evaluated, 5) + rolling_rows(
        prices, weights_by_name, evaluated, 10
    )
    pd.DataFrame(rolling).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in (0.001, 0.002, 0.005):
        for name in evaluated:
            fee_rows.append(
                {
                    "fee_rate": fee,
                    "model": name,
                    **summarize(run(prices, weights_by_name[name], ACTUAL_START, PRE_2026_END, fee)),
                }
            )
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    hashes = {
        name: hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
        for name in ("QQQ.csv", "TQQQ.csv")
    }
    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "selection_data_end": PRE_2026_END.date().isoformat(),
        "lookback_sessions": 30,
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "variant_count": len(specs),
        "shortlist_limit": 20,
        "screen": {
            "full_pre2026_cagr_delta_min": -0.005,
            "actual_pre2026_cagr_delta_min": 0.0,
            "decade_2016_2025_cagr_delta_min": 0.0,
            "full_pre2026_mdd_delta_min": -0.02,
            "actual_pre2026_mdd_delta_min": -0.02,
            "actual_pre2026_annual_trades_max": 20.0,
        },
        "shortlist": shortlist,
        "asset_sha256": hashes,
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
