#!/usr/bin/env python3
"""List consecutive default-VO volatility regimes and TQQQ price returns."""

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

from backtests import load_market_data


ACTUAL_TQQQ_START = pd.Timestamp("2010-02-11")
BAND_ORDER = ("warmup", "at_or_below_60", "above_60_at_or_below_90", "above_90")


def vo_regime_rows(prices: pd.DataFrame) -> pd.DataFrame:
    volatility = prices["Close"].pct_change().rolling(30).std(ddof=1) * np.sqrt(252)
    band = pd.Series(
        np.select(
            [volatility <= 0.60, volatility <= 0.90],
            ["at_or_below_60", "above_60_at_or_below_90"],
            default="above_90",
        ),
        index=prices.index,
        dtype="object",
    )
    band.loc[volatility.isna()] = "warmup"
    origin = pd.Series(
        np.where(prices.index < ACTUAL_TQQQ_START, "synthetic", "actual"),
        index=prices.index,
    )
    group = ((band != band.shift()) | (origin != origin.shift())).cumsum()
    next_session = pd.Series(prices.index, index=prices.index).shift(-1)

    rows: list[dict[str, object]] = []
    for regime_id, dates in band.groupby(group).groups.items():
        start = dates[0]
        end = dates[-1]
        start_price = float(prices.loc[start, "Close"])
        end_price = float(prices.loc[end, "Close"])
        label = str(band.loc[start])
        rows.append(
            {
                "regime_id": int(regime_id),
                "signal_start": start,
                "signal_end": end,
                "band": label,
                "target_tqqq_weight": {
                    "warmup": 1.0,
                    "at_or_below_60": 1.0,
                    "above_60_at_or_below_90": 0.5,
                    "above_90": 0.0,
                }[label],
                "data_origin": str(origin.loc[start]),
                "execution_start": next_session.loc[start],
                "trading_days": len(dates),
                "start_close": start_price,
                "end_close": end_price,
                "tqqq_return": end_price / start_price - 1.0,
                "start_volatility": None if pd.isna(volatility.loc[start]) else float(volatility.loc[start]),
                "end_volatility": None if pd.isna(volatility.loc[end]) else float(volatility.loc[end]),
            }
        )
    return pd.DataFrame(rows)


def summarize_regimes(regimes: pd.DataFrame) -> pd.DataFrame:
    usable = regimes.loc[regimes["band"] != "warmup"].copy()
    grouped = usable.groupby(["data_origin", "band"], sort=False)
    summary = grouped.agg(
        regime_count=("regime_id", "size"),
        trading_days=("trading_days", "sum"),
        average_return=("tqqq_return", "mean"),
        median_return=("tqqq_return", "median"),
        win_rate=("tqqq_return", lambda values: float((values > 0.0).mean())),
        best_return=("tqqq_return", "max"),
        worst_return=("tqqq_return", "min"),
    ).reset_index()
    order = {name: position for position, name in enumerate(BAND_ORDER)}
    summary["band_order"] = summary["band"].map(order)
    return summary.sort_values(["data_origin", "band_order"]).drop(columns="band_order")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "vo-regimes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prices = load_market_data(ROOT).tqqq
    regimes = vo_regime_rows(prices)
    summary = summarize_regimes(regimes)
    args.output.mkdir(parents=True, exist_ok=True)
    regimes.to_csv(args.output / "regimes.csv", index=False, date_format="%Y-%m-%d", float_format="%.10f")
    summary.to_csv(args.output / "summary.csv", index=False, float_format="%.10f")
    metadata = {
        "generated_through": prices.index[-1].date().isoformat(),
        "price_field": "TQQQ adjusted close",
        "return_formula": "end_close / start_close - 1",
        "signal_rule": "30-session TQQQ adjusted-close return volatility, annualized with sqrt(252)",
        "actual_tqqq_start": ACTUAL_TQQQ_START.date().isoformat(),
        "tqqq_sha256": hashlib.sha256((ROOT / "assets" / "TQQQ.csv").read_bytes()).hexdigest(),
    }
    (args.output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
