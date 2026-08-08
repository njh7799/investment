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
from backtests.ma_research import build_ma_weights


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
BENCHMARKS = ("vo", "tqqq_hold", "qqq_hold")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze moving-average and VO-linked variants")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(prices_by_name, weights_by_name, name, start=None, end=None, fee=0.001):
    return run_weight_strategy(
        prices_by_name[name], weights_by_name[name], start=start, end=end, fee_rate=fee
    )


def month_starts(index: pd.DatetimeIndex, years: int) -> list[pd.Timestamp]:
    last_start = PRE_2026_END - pd.DateOffset(years=years)
    eligible = index[(index >= ACTUAL_START) & (index <= last_start)]
    values = pd.Series(eligible, index=eligible)
    return list(values.groupby(eligible.to_period("M")).first())


def rolling_rows(prices_by_name, weights_by_name, names, years):
    rows = []
    index = prices_by_name["vo"].index
    for name in names:
        metrics = []
        for start in month_starts(index, years):
            end = min(start + pd.DateOffset(years=years), PRE_2026_END)
            metrics.append(summarize(run(prices_by_name, weights_by_name, name, start, end)))
        rows.append(
            {
                "model": name,
                "window_years": years,
                "window_count": len(metrics),
                "median_cagr": float(pd.Series([item["cagr"] for item in metrics]).median()),
                "worst_cagr": min(float(item["cagr"]) for item in metrics),
                "median_mdd": float(pd.Series([item["mdd"] for item in metrics]).median()),
                "worst_mdd": min(float(item["mdd"]) for item in metrics),
                "median_longest_tuw_days": float(
                    pd.Series([item["longest_time_underwater_days"] for item in metrics]).median()
                ),
                "worst_longest_tuw_days": max(
                    int(item["longest_time_underwater_days"]) for item in metrics
                ),
            }
        )
    return rows


def screen_variants(period: pd.DataFrame, families: dict[str, str]) -> pd.DataFrame:
    indexed = period.set_index(["period", "model"])
    baseline = {name: indexed.loc[(name, "vo")] for name in PERIODS}
    rows = []
    for model, family in families.items():
        full = indexed.loc[("full_pre2026", model)]
        actual = indexed.loc[("actual_pre2026", model)]
        decade = indexed.loc[("decade_2016_2025", model)]
        deltas = {
            "full_cagr_delta": float(full.cagr - baseline["full_pre2026"].cagr),
            "actual_cagr_delta": float(actual.cagr - baseline["actual_pre2026"].cagr),
            "decade_cagr_delta": float(decade.cagr - baseline["decade_2016_2025"].cagr),
            "full_mdd_delta": float(full.mdd - baseline["full_pre2026"].mdd),
            "actual_mdd_delta": float(actual.mdd - baseline["actual_pre2026"].mdd),
        }
        if family == "vo_linked":
            passed = (
                deltas["full_cagr_delta"] >= -0.005
                and deltas["actual_cagr_delta"] >= 0.0
                and deltas["decade_cagr_delta"] >= 0.0
                and deltas["full_mdd_delta"] >= -0.02
                and deltas["actual_mdd_delta"] >= -0.02
                and float(actual.annual_trades) <= 20.0
            )
        else:
            passed = (
                deltas["full_cagr_delta"] >= -0.03
                and deltas["actual_cagr_delta"] >= -0.02
                and deltas["decade_cagr_delta"] >= -0.02
                and deltas["full_mdd_delta"] >= -0.10
                and deltas["actual_mdd_delta"] >= -0.10
                and float(actual.annual_trades) <= 20.0
            )
        rows.append(
            {
                "model": model,
                "family": family,
                "screen_pass": passed,
                **deltas,
                "actual_annual_trades": float(actual.annual_trades),
                "rank_floor": min(
                    deltas["full_cagr_delta"],
                    deltas["actual_cagr_delta"],
                    deltas["decade_cagr_delta"],
                ),
                "rank_sum": sum(
                    deltas[name]
                    for name in ("full_cagr_delta", "actual_cagr_delta", "decade_cagr_delta")
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["family", "screen_pass", "rank_floor", "rank_sum"],
        ascending=[True, False, False, False],
    )


def shortlist_variants(screen, weights_by_name):
    selection_mask = weights_by_name["vo"].index <= PRE_2026_END
    base_digest = hashlib.sha256(
        weights_by_name["vo"].loc[selection_mask].to_numpy().tobytes()
    ).hexdigest()
    seen = {base_digest: "vo"}
    duplicate_of: dict[str, str | None] = {}
    changed_pre2026: dict[str, int] = {}
    changed_current: dict[str, int] = {}
    shortlisted: dict[str, list[str]] = {"standalone": [], "vo_linked": []}
    for model in screen.model:
        weights = weights_by_name[model]
        digest = hashlib.sha256(weights.loc[selection_mask].to_numpy().tobytes()).hexdigest()
        duplicate_of[model] = seen.get(digest)
        changed_pre2026[model] = int(
            (weights.loc[selection_mask] != weights_by_name["vo"].loc[selection_mask]).sum()
        )
        changed_current[model] = int((weights != weights_by_name["vo"]).sum())
        if digest in seen:
            continue
        seen[digest] = model
        family = str(screen.loc[screen.model == model, "family"].iloc[0])
        if len(shortlisted[family]) < 10:
            shortlisted[family].append(model)
    result = screen.copy()
    result["changed_target_days_pre2026"] = result.model.map(changed_pre2026)
    result["changed_target_days_current"] = result.model.map(changed_current)
    result["duplicate_of"] = result.model.map(duplicate_of)
    return result, [*shortlisted["standalone"], *shortlisted["vo_linked"]]


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    tqqq, variant_weights, specs = build_ma_weights(data)
    index = data.index
    prices_by_name = {name: tqqq for name in variant_weights}
    weights_by_name = dict(variant_weights)
    prices_by_name["tqqq_hold"] = tqqq
    weights_by_name["tqqq_hold"] = pd.Series(1.0, index=index)
    prices_by_name["qqq_hold"] = data.qqq.loc[index]
    weights_by_name["qqq_hold"] = pd.Series(1.0, index=index)
    families = {spec.name: spec.family for spec in specs}
    pd.DataFrame([spec.__dict__ for spec in specs]).to_csv(args.output / "variants.csv", index=False)

    period_rows = []
    for period_name, (start, end) in PERIODS.items():
        for name in [*BENCHMARKS, *families]:
            period_rows.append(
                {
                    "period": period_name,
                    "model": name,
                    **summarize(run(prices_by_name, weights_by_name, name, start, end)),
                }
            )
    period = pd.DataFrame(period_rows)
    period.to_csv(args.output / "period-summary.csv", index=False, float_format="%.10f")

    screen = screen_variants(period, families)
    screen, shortlist = shortlist_variants(screen, weights_by_name)
    screen.to_csv(args.output / "screening-summary.csv", index=False, float_format="%.10f")
    evaluated = [*BENCHMARKS, *shortlist]

    stress_rows = []
    for period_name, (start, end) in STRESS.items():
        for name in evaluated:
            stress_rows.append(
                {
                    "period": period_name,
                    "model": name,
                    **summarize(run(prices_by_name, weights_by_name, name, start, end)),
                }
            )
    pd.DataFrame(stress_rows).to_csv(args.output / "stress-summary.csv", index=False, float_format="%.10f")

    annual_rows = []
    for year in range(2010, 2026):
        for name in evaluated:
            annual_rows.append(
                {
                    "year": year,
                    "model": name,
                    **summarize(
                        run(
                            prices_by_name,
                            weights_by_name,
                            name,
                            f"{year}-01-01",
                            f"{year}-12-31",
                        )
                    ),
                }
            )
    pd.DataFrame(annual_rows).to_csv(args.output / "annual-summary.csv", index=False, float_format="%.10f")

    rolling = rolling_rows(prices_by_name, weights_by_name, evaluated, 5)
    rolling += rolling_rows(prices_by_name, weights_by_name, evaluated, 10)
    pd.DataFrame(rolling).to_csv(args.output / "rolling-summary.csv", index=False, float_format="%.10f")

    fee_rows = []
    for fee in (0.001, 0.002, 0.005):
        for name in evaluated:
            fee_rows.append(
                {
                    "fee_rate": fee,
                    "model": name,
                    **summarize(
                        run(
                            prices_by_name,
                            weights_by_name,
                            name,
                            ACTUAL_START,
                            PRE_2026_END,
                            fee,
                        )
                    ),
                }
            )
    pd.DataFrame(fee_rows).to_csv(args.output / "fee-summary.csv", index=False, float_format="%.10f")

    metadata = {
        "generated_through": data.index[-1].date().isoformat(),
        "selection_data_end": PRE_2026_END.date().isoformat(),
        "initial_cash": 100_000,
        "base_fee_rate": 0.001,
        "variant_count": len(specs),
        "shortlist": shortlist,
        "asset_sha256": {
            name: hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
            for name in ("QQQ.csv", "TQQQ.csv")
        },
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
