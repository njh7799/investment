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

from backtests import load_market_data, summarize
from backtests.vo_consecutive import build_vo_consecutive_weights
from scripts.analyze_vo_rebound import (
    PERIODS,
    SELECTION_END,
    STRESS,
    promotion_rows,
    rolling_rows,
    run,
)

BUILDER = build_vo_consecutive_weights
DESCRIPTION = "Analyze preregistered VO consecutive-up variants"
PREREGISTRATION = "docs/research/preregistrations/batch-14-vo-consecutive-up.yaml"
PREREGISTERED_COMMIT = "2f4edc0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


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


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_market_data(ROOT)
    prices, weights_by_name, specs = BUILDER(data)
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
    selection = base.index <= SELECTION_END
    seen = {hashlib.sha256(base.loc[selection].to_numpy().tobytes()).hexdigest(): "vo"}
    for model in candidates:
        screen.loc[screen.model == model, "changed_target_days"] = int((weights_by_name[model] != base).sum())
        digest = hashlib.sha256(weights_by_name[model].loc[selection].to_numpy().tobytes()).hexdigest()
        screen.loc[screen.model == model, "duplicate_of"] = seen.get(digest)
        if digest not in seen:
            seen[digest] = model
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
        "preregistration": PREREGISTRATION,
        "preregistered_commit": PREREGISTERED_COMMIT,
        "candidate_count": len(candidates),
        "unique_pre2026_target_paths_including_vo": len(seen),
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
