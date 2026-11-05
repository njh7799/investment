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
from backtests.vo_rebound import build_vo_rebound_weights


SELECTION_END = pd.Timestamp("2025-12-31")
PERIODS = {
    "full_current": (None, None),
    "full_pre2026": (None, SELECTION_END),
    "decade_2016_2025": (pd.Timestamp("2016-01-01"), SELECTION_END),
    "recent_two_year_diagnostic": (pd.Timestamp("2024-11-04"), None),
    "current_ytd_diagnostic": (pd.Timestamp("2026-01-01"), None),
}
STRESS = {
    "dotcom": ("2000-03-10", "2002-10-09"),
    "global_financial_crisis": ("2007-10-31", "2009-03-09"),
    "covid_crash": ("2020-02-19", "2020-03-23"),
    "2022_bear": ("2021-11-19", "2022-12-28"),
    "2025_rebound": ("2025-02-19", "2025-08-12"),
    "2026_rebound": ("2026-01-02", None),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze preregistered VO rebound-entry variants")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(prices, weights, start=None, end=None, fee=0.001):
    return run_weight_strategy(prices, weights, start=start, end=end, fee_rate=fee)


def month_starts(index: pd.DatetimeIndex, years: int) -> list[pd.Timestamp]:
    last_start = index[-1] - pd.DateOffset(years=years)
    eligible = index[index <= last_start]
    return list(pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first())


def rolling_rows(prices, weights_by_name, names: list[str], years: int) -> list[dict[str, object]]:
    rows = []
    for name in names:
        metrics = [
            summarize(run(prices, weights_by_name[name], start, start + pd.DateOffset(years=years)))
            for start in month_starts(prices.index, years)
        ]
        rows.append({
            "model": name,
            "window_years": years,
            "window_count": len(metrics),
            "median_cagr": float(pd.Series([m["cagr"] for m in metrics]).median()),
            "worst_cagr": float(min(m["cagr"] for m in metrics)),
            "median_mdd": float(pd.Series([m["mdd"] for m in metrics]).median()),
            "worst_mdd": float(min(m["mdd"] for m in metrics)),
            "median_longest_tuw_days": float(pd.Series([m["longest_time_underwater_days"] for m in metrics]).median()),
            "worst_longest_tuw_days": int(max(m["longest_time_underwater_days"] for m in metrics)),
        })
    return rows


def screen_rows(period: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    indexed = period.set_index(["period", "model"])
    rows = []
    for model in candidates:
        full = indexed.loc[("full_pre2026", model)]
        full_base = indexed.loc[("full_pre2026", "vo")]
        decade = indexed.loc[("decade_2016_2025", model)]
        decade_base = indexed.loc[("decade_2016_2025", "vo")]
        passed = (
            full.cagr - full_base.cagr >= -0.005
            and decade.cagr > decade_base.cagr
            and full.mdd - full_base.mdd >= -0.02
            and full.annual_trades <= 20.0
        )
        rows.append({
            "model": model,
            "eligible_new_candidate": True,
            "screen_pass": bool(passed),
            "full_pre2026_cagr_delta": float(full.cagr - full_base.cagr),
            "full_pre2026_mdd_delta": float(full.mdd - full_base.mdd),
            "decade_2016_2025_cagr_delta": float(decade.cagr - decade_base.cagr),
            "decade_2016_2025_mdd_delta": float(decade.mdd - decade_base.mdd),
            "full_annual_trades": float(full.annual_trades),
        })
    return pd.DataFrame(rows)


def family_for(model: str) -> str:
    for prefix in ("one_", "cool20_", "cool60_", "hold10_", "hold20_", "trail10_", "trail15_", "staged_"):
        if model.startswith(prefix):
            return prefix.rstrip("_")
    if model.startswith("streak_"):
        return "consecutive_up_fill_stop_" + model.split("_")[1]
    if model.startswith("combo_"):
        return "consecutive_up_return_fill_stop_" + model.split("_")[1]
    if model.startswith("online_low"):
        return "online_low_rebound_fill_stop"
    if model.startswith("surge_5d"):
        return "five_day_surge_fill_stop"
    if model.startswith("strict_high"):
        return "return_with_strict_recent_high_fill_stop"
    if model.startswith("near_high"):
        return "return_with_near_recent_high_fill_stop"
    if model.startswith("sma_upcross"):
        return "sma_upcross_fill_stop"
    raise ValueError(f"unknown model family: {model}")


def promotion_rows(
    candidates: list[str],
    period: pd.DataFrame,
    rolling: pd.DataFrame,
    stress: pd.DataFrame,
    annual: pd.DataFrame,
    fee: pd.DataFrame,
    screen: pd.DataFrame,
) -> pd.DataFrame:
    p = period.set_index(["period", "model"])
    r = rolling.set_index(["window_years", "model"])
    s = stress.set_index(["period", "model"])
    a = annual.set_index(["year", "model"])
    f = fee.set_index(["fee_rate", "period", "model"])
    sc = screen.set_index("model")
    preliminary: dict[str, dict[str, object]] = {}
    for model in candidates:
        rolling_pass = all(
            r.loc[(years, model), metric] > r.loc[(years, "vo"), metric]
            for years in (5, 10) for metric in ("median_cagr", "worst_cagr")
        )
        stress_pass = all(
            s.loc[(name, model), "mdd"] - s.loc[(name, "vo"), "mdd"] >= -0.05
            for name in STRESS
        )
        current = p.loc[("full_current", model)]
        current_base = p.loc[("full_current", "vo")]
        full_risk_pass = (
            current.mdd >= current_base.mdd - abs(current_base.mdd) * 0.05
            and current.longest_time_underwater_days <= current_base.longest_time_underwater_days * 1.05
        )
        fee_pass = all(
            f.loc[(0.002, name, model), "cagr"] > f.loc[(0.002, name, "vo"), "cagr"]
            for name in ("full_pre2026", "decade_2016_2025")
        )
        years = sorted(year for year in set(annual.year) if year <= SELECTION_END.year)
        differences = pd.Series({
            year: a.loc[(year, model), "total_return"] - a.loc[(year, "vo"), "total_return"]
            for year in years
        })
        positives = differences[differences > 1e-12]
        largest_share = float(positives.max() / positives.sum()) if not positives.empty else 1.0
        annual_pass = len(positives) >= 3 and largest_share <= 0.5
        preliminary[model] = {
            "model": model,
            "family": family_for(model),
            "screen_pass": bool(sc.loc[model, "screen_pass"]),
            "rolling_pass": rolling_pass,
            "stress_pass": stress_pass,
            "full_risk_pass": full_risk_pass,
            "fee_0_2_pass": fee_pass,
            "positive_excess_years": len(positives),
            "largest_positive_year_share": largest_share,
            "annual_distribution_pass": annual_pass,
        }
    rows = []
    for model, row in preliminary.items():
        siblings = [item for item in preliminary.values() if item["family"] == row["family"]]
        adjacent_pass = sum(bool(item["screen_pass"] and item["rolling_pass"]) for item in siblings) >= 2
        gates = (
            row["screen_pass"], row["rolling_pass"], row["stress_pass"],
            row["full_risk_pass"], row["fee_0_2_pass"], row["annual_distribution_pass"],
            adjacent_pass,
        )
        rows.append({
            **row,
            "adjacent_parameter_pass": adjacent_pass,
            "all_historical_gates_pass": all(gates),
            "promotion_status": "observation_only_pending_new_cycle" if all(gates) else "research_record",
        })
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    prices, weights_by_name, specs = build_vo_rebound_weights(data)
    candidates = [spec.name for spec in specs]
    names = ["vo", *candidates]
    pd.DataFrame([spec.__dict__ for spec in specs]).to_csv(args.output / "variants.csv", index=False)

    period_rows = []
    for period_name, (start, end) in PERIODS.items():
        for name in names:
            period_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights_by_name[name], start, end))})
    period = pd.DataFrame(period_rows)
    period.to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    screen = screen_rows(period, candidates)
    base = weights_by_name["vo"]
    for model in candidates:
        screen.loc[screen.model == model, "changed_target_days"] = int((weights_by_name[model] != base).sum())
    screen.to_csv(args.output / "screening-summary.csv", index=False, float_format="%.10f")

    stress_rows = []
    for period_name, (start, end) in STRESS.items():
        for name in names:
            stress_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights_by_name[name], start, end))})
    stress = pd.DataFrame(stress_rows)
    stress.to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    annual_rows = []
    for year in range(prices.index[0].year, prices.index[-1].year + 1):
        for name in names:
            annual_rows.append({"year": year, "model": name, **summarize(run(prices, weights_by_name[name], f"{year}-01-01", f"{year}-12-31"))})
    annual = pd.DataFrame(annual_rows)
    annual.to_csv(args.output / "annual-summary.csv", index=False, float_format="%.10f")

    rolling = pd.DataFrame(
        rolling_rows(prices, weights_by_name, names, 5)
        + rolling_rows(prices, weights_by_name, names, 10)
    )
    rolling.to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee_rate in (0.001, 0.002, 0.005):
        for period_name, start, end in (
            ("full_pre2026", None, SELECTION_END),
            ("decade_2016_2025", pd.Timestamp("2016-01-01"), SELECTION_END),
        ):
            for name in names:
                fee_rows.append({
                    "fee_rate": fee_rate, "period": period_name, "model": name,
                    **summarize(run(prices, weights_by_name[name], start, end, fee_rate)),
                })
    fee = pd.DataFrame(fee_rows)
    fee.to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    promotion = promotion_rows(candidates, period, rolling, stress, annual, fee, screen)
    promotion.to_csv(args.output / "promotion-audit.csv", index=False, float_format="%.10f")

    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "interpretation": "retrospective development; no historical period is an unseen holdout",
        "preregistration": "docs/research/preregistrations/batch-13-vo-rebound-entry.yaml",
        "preregistered_commit": "7b9e82a",
        "candidate_count": len(candidates),
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "asset_sha256": {
            name: hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
            for name in ("QQQ.csv", "TQQQ.csv")
        },
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
