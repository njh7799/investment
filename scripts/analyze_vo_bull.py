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

from backtests import load_assets, load_market_data, run_weight_strategy, summarize
from backtests.vo_bull import build_vo_bull_weights


ACTUAL_START = pd.Timestamp("2010-02-11")
SELECTION_END = pd.Timestamp("2025-12-31")
PERIODS = {
    "full_pre2026": (None, SELECTION_END),
    "actual_pre2026": (ACTUAL_START, SELECTION_END),
    "decade_2016_2025": (pd.Timestamp("2016-01-01"), SELECTION_END),
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
    parser = argparse.ArgumentParser(description="Analyze preregistered VO bull-participation variants")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-only", action="store_true")
    return parser.parse_args()


def run(prices, weights, start=None, end=None, fee=0.001):
    return run_weight_strategy(prices, weights, start=start, end=end, fee_rate=fee)


def month_starts(index: pd.DatetimeIndex, years: int) -> list[pd.Timestamp]:
    last_start = SELECTION_END - pd.DateOffset(years=years)
    eligible = index[(index >= ACTUAL_START) & (index <= last_start)]
    return list(pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first())


def rolling_rows(prices, weights_by_name, names: list[str], years: int) -> list[dict[str, object]]:
    rows = []
    starts = month_starts(prices.index, years)
    for name in names:
        metrics = [
            summarize(run(prices, weights_by_name[name], start, min(start + pd.DateOffset(years=years), SELECTION_END)))
            for start in starts
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


def screen_rows(period: pd.DataFrame) -> pd.DataFrame:
    indexed = period.set_index(["period", "model"])
    rows = []
    for model in period.model.unique():
        if model == "vo":
            continue
        values = {name: indexed.loc[(name, model)] for name in ("full_pre2026", "actual_pre2026", "decade_2016_2025")}
        base = {name: indexed.loc[(name, "vo")] for name in values}
        deltas = {
            f"{name}_{metric}_delta": float(values[name][metric] - base[name][metric])
            for name in values for metric in ("cagr", "mdd")
        }
        passed = (
            deltas["full_pre2026_cagr_delta"] >= -0.005
            and deltas["actual_pre2026_cagr_delta"] > 0.0
            and deltas["decade_2016_2025_cagr_delta"] > 0.0
            and deltas["full_pre2026_mdd_delta"] >= -0.02
            and deltas["actual_pre2026_mdd_delta"] >= -0.02
            and float(values["actual_pre2026"].annual_trades) <= 20.0
        )
        rows.append({
            "model": model,
            "screen_pass": passed,
            **deltas,
            "actual_annual_trades": float(values["actual_pre2026"].annual_trades),
            "rank_floor": min(
                deltas["full_pre2026_cagr_delta"],
                deltas["actual_pre2026_cagr_delta"],
                deltas["decade_2016_2025_cagr_delta"],
            ),
            "rank_sum": sum(deltas[key] for key in deltas if key.endswith("cagr_delta")),
        })
    return pd.DataFrame(rows).sort_values(["screen_pass", "rank_floor", "rank_sum"], ascending=[False, False, False])


def write_promotion_audit(output: Path) -> None:
    metadata = json.loads((output / "metadata.json").read_text())
    models = metadata["shortlist"]
    period = pd.read_csv(output / "period-summary.csv").set_index(["period", "model"])
    rolling = pd.read_csv(output / "rolling-summary.csv").set_index(["window_years", "model"])
    stress = pd.read_csv(output / "stress-summary.csv").set_index(["period", "model"])
    annual = pd.read_csv(output / "annual-summary.csv").set_index(["year", "model"])
    fee = pd.read_csv(output / "fee-summary.csv").set_index(["fee_rate", "period", "model"])
    rows = []
    for model in models:
        rolling_pass = all(
            rolling.loc[(years, model), metric] > rolling.loc[(years, "vo"), metric]
            for years in (5, 10) for metric in ("median_cagr", "worst_cagr")
        )
        stress_pass = all(
            stress.loc[(name, model), "mdd"] - stress.loc[(name, "vo"), "mdd"] >= -0.05
            for name in STRESS
        )
        actual = period.loc[("actual_pre2026", model)]
        actual_base = period.loc[("actual_pre2026", "vo")]
        actual_risk_pass = (
            actual.mdd >= actual_base.mdd - abs(actual_base.mdd) * 0.05
            and actual.longest_time_underwater_days <= actual_base.longest_time_underwater_days * 1.05
        )
        fee_pass = all(
            fee.loc[(0.002, name, model), "cagr"] > fee.loc[(0.002, name, "vo"), "cagr"]
            for name in ("actual_pre2026", "decade_2016_2025")
        )
        differences = pd.Series({
            year: annual.loc[(year, model), "total_return"] - annual.loc[(year, "vo"), "total_return"]
            for year in range(2010, 2026)
        })
        positives = differences[differences > 1e-12]
        largest_share = float(positives.max() / positives.sum()) if not positives.empty else 1.0
        annual_distribution_pass = len(positives) >= 3 and largest_share <= 0.5
        rows.append({
            "model": model,
            "rolling_pass": rolling_pass,
            "stress_pass": stress_pass,
            "actual_risk_pass": actual_risk_pass,
            "fee_0_2_pass": fee_pass,
            "positive_excess_years": len(positives),
            "largest_positive_year_share": largest_share,
            "annual_distribution_pass": annual_distribution_pass,
            "all_non_parameter_gates_pass": all((rolling_pass, stress_pass, actual_risk_pass, fee_pass, annual_distribution_pass)),
        })
    pd.DataFrame(rows).to_csv(output / "promotion-audit.csv", index=False, float_format="%.10f")


def main() -> int:
    args = parse_args()
    if args.audit_only:
        write_promotion_audit(args.output)
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    extra = load_assets(("SPY", "IWM"), ROOT)
    breadth_closes = pd.concat({
        "QQQ": data.qqq["Close"], "SPY": extra["SPY"]["Close"], "IWM": extra["IWM"]["Close"]
    }, axis=1)
    prices, weights_by_name, specs = build_vo_bull_weights(data, breadth_closes)
    pd.DataFrame([spec.__dict__ for spec in specs]).to_csv(args.output / "variants.csv", index=False)

    period_rows = []
    for period_name, (start, end) in PERIODS.items():
        for name, weights in weights_by_name.items():
            period_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights, start, end))})
    period = pd.DataFrame(period_rows)
    period.to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    screen = screen_rows(period)
    selection = weights_by_name["vo"].index <= SELECTION_END
    seen = {hashlib.sha256(weights_by_name["vo"].loc[selection].to_numpy().tobytes()).hexdigest(): "vo"}
    duplicate_of = {}
    changed_pre2026 = {}
    changed_current = {}
    shortlist = []
    for model in screen.model:
        weights = weights_by_name[model]
        digest = hashlib.sha256(weights.loc[selection].to_numpy().tobytes()).hexdigest()
        duplicate_of[model] = seen.get(digest)
        changed_pre2026[model] = int((weights.loc[selection] != weights_by_name["vo"].loc[selection]).sum())
        changed_current[model] = int((weights != weights_by_name["vo"]).sum())
        if digest not in seen:
            seen[digest] = model
            if bool(screen.loc[screen.model == model, "screen_pass"].iloc[0]) and len(shortlist) < 20:
                shortlist.append(model)
    screen["changed_target_days_pre2026"] = screen.model.map(changed_pre2026)
    screen["changed_target_days_current"] = screen.model.map(changed_current)
    screen["duplicate_of"] = screen.model.map(duplicate_of)
    screen.to_csv(args.output / "screening-summary.csv", index=False, float_format="%.10f")
    evaluated = ["vo", *shortlist]

    stress_rows = []
    for period_name, (start, end) in STRESS.items():
        for name in evaluated:
            stress_rows.append({"period": period_name, "model": name, **summarize(run(prices, weights_by_name[name], start, end))})
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    annual_rows = []
    for year in range(2010, 2026):
        for name in evaluated:
            annual_rows.append({"year": year, "model": name, **summarize(run(prices, weights_by_name[name], f"{year}-01-01", f"{year}-12-31"))})
    pd.DataFrame(annual_rows).to_csv(args.output / "annual-summary.csv", index=False, float_format="%.10f")

    rolling = rolling_rows(prices, weights_by_name, evaluated, 5) + rolling_rows(prices, weights_by_name, evaluated, 10)
    pd.DataFrame(rolling).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in (0.001, 0.002, 0.005):
        for period_name, start in (("actual_pre2026", ACTUAL_START), ("decade_2016_2025", pd.Timestamp("2016-01-01"))):
            for name in evaluated:
                fee_rows.append({"fee_rate": fee, "period": period_name, "model": name, **summarize(run(prices, weights_by_name[name], start, SELECTION_END, fee))})
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    hashes = {
        name: hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
        for name in ("QQQ.csv", "TQQQ.csv", "SPY.csv", "IWM.csv")
    }
    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "selection_data_end": SELECTION_END.date().isoformat(),
        "preregistration": "docs/research/preregistrations/batch-08-vo-bull-participation.yaml",
        "preregistered_commit": "d5ec4cc",
        "variant_count": len(specs),
        "shortlist_limit": 20,
        "shortlist": shortlist,
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "asset_sha256": hashes,
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    write_promotion_audit(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
