#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (5, 20, 60, 120, 252)
RATIO_THRESHOLDS = (0.0, 0.25, 0.5, 0.75, 1.0)
RETURN_THRESHOLDS = (0.0, 0.01, 0.02, 0.03)
ERA_BOUNDS = (
    ("1971-1999", None, pd.Timestamp("1999-12-31")),
    ("2000-2009", pd.Timestamp("2000-01-01"), pd.Timestamp("2009-12-31")),
    ("2010-latest", pd.Timestamp("2010-01-01"), None),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze IXIC crash-day/next-day rebound patterns")
    parser.add_argument("--input", type=Path, default=ROOT / "assets" / "IXIC.csv")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_ixic(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    expected = ["Date", "Open", "High", "Low", "Close"]
    if list(frame.columns) != expected:
        raise ValueError(f"unexpected IXIC columns: {list(frame.columns)}")
    frame["Date"] = pd.to_datetime(frame["Date"], format="%Y.%m.%d")
    if frame["Date"].duplicated().any() or not frame["Date"].is_monotonic_increasing:
        raise ValueError("IXIC dates must be unique and increasing")
    if frame[expected[1:]].isna().any().any() or (frame[expected[1:]] <= 0).any().any():
        raise ValueError("IXIC OHLC must be positive and complete")
    if (frame["High"] < frame[["Open", "Low", "Close"]].max(axis=1)).any():
        raise ValueError("IXIC High violates the OHLC invariant")
    if (frame["Low"] > frame[["Open", "High", "Close"]].min(axis=1)).any():
        raise ValueError("IXIC Low violates the OHLC invariant")
    return frame.set_index("Date")


def build_events(prices: pd.DataFrame, crash_threshold: float = -0.03, cooldown: int = 20) -> pd.DataFrame:
    close = prices["Close"].to_numpy(dtype=float)
    dates = prices.index
    returns = prices["Close"].pct_change().to_numpy(dtype=float)
    crash_positions = np.flatnonzero(returns <= crash_threshold)
    rows: list[dict[str, object]] = []
    previous_crash_position: int | None = None
    for position in crash_positions:
        if position + 1 >= len(prices):
            continue
        event_return = returns[position]
        next_return = returns[position + 1]
        row: dict[str, object] = {
            "event_date": dates[position],
            "rebound_date": dates[position + 1],
            "event_return": event_return,
            "next_day_return": next_return,
            "rebound_ratio": next_return / abs(event_return),
            "exact_gap_recovery": (close[position + 1] - close[position]) / (close[position - 1] - close[position]),
            "episode_first": previous_crash_position is None or position - previous_crash_position > cooldown,
            "sessions_since_previous_crash": np.nan if previous_crash_position is None else position - previous_crash_position,
        }
        if event_return > -0.04:
            row["drop_bucket"] = "-3% to -4%"
        elif event_return > -0.05:
            row["drop_bucket"] = "-4% to -5%"
        else:
            row["drop_bucket"] = "-5% or worse"
        base_position = position + 1
        for horizon in HORIZONS:
            end_position = base_position + horizon
            if end_position >= len(prices):
                row[f"return_{horizon}d"] = np.nan
                row[f"min_return_{horizon}d"] = np.nan
                row[f"max_return_{horizon}d"] = np.nan
                row[f"precrash_recovered_{horizon}d"] = np.nan
                continue
            path = close[base_position : end_position + 1] / close[base_position] - 1.0
            row[f"return_{horizon}d"] = path[-1]
            row[f"min_return_{horizon}d"] = path.min()
            row[f"max_return_{horizon}d"] = path.max()
            row[f"precrash_recovered_{horizon}d"] = bool(
                np.any(close[base_position + 1 : end_position + 1] >= close[position - 1])
            )
        rows.append(row)
        previous_crash_position = position
    return pd.DataFrame(rows)


def _holm_adjust(pvalues: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=pvalues.index, dtype=float)
    valid = pvalues.dropna().sort_values()
    running = 0.0
    count = len(valid)
    for rank, (index, value) in enumerate(valid.items()):
        adjusted = min(1.0, (count - rank) * value)
        running = max(running, adjusted)
        result.loc[index] = running
    return result


def compare_thresholds(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    samples = {"all_events": events, "episode_first": events[events["episode_first"]]}
    definitions = {
        "rebound_ratio": RATIO_THRESHOLDS,
        "next_day_return": RETURN_THRESHOLDS,
    }
    for sample_name, sample in samples.items():
        for measure, thresholds in definitions.items():
            for threshold in thresholds:
                for horizon in HORIZONS:
                    outcome = f"return_{horizon}d"
                    eligible = sample[[measure, outcome]].dropna()
                    high = eligible.loc[eligible[measure] >= threshold, outcome]
                    low = eligible.loc[eligible[measure] < threshold, outcome]
                    if high.empty or low.empty:
                        continue
                    fisher = stats.fisher_exact(
                        [
                            [(high > 0).sum(), (high <= 0).sum()],
                            [(low > 0).sum(), (low <= 0).sum()],
                        ]
                    )
                    mann_whitney = stats.mannwhitneyu(high, low, alternative="two-sided")
                    rows.append(
                        {
                            "sample": sample_name,
                            "measure": measure,
                            "threshold": threshold,
                            "horizon_days": horizon,
                            "high_n": len(high),
                            "low_n": len(low),
                            "high_median_return": high.median(),
                            "low_median_return": low.median(),
                            "median_return_difference": high.median() - low.median(),
                            "high_positive_rate": (high > 0).mean(),
                            "low_positive_rate": (low > 0).mean(),
                            "positive_rate_difference": (high > 0).mean() - (low > 0).mean(),
                            "mann_whitney_p": mann_whitney.pvalue,
                            "fisher_p": fisher.pvalue,
                        }
                    )
    result = pd.DataFrame(rows)
    for column in ("mann_whitney_p", "fisher_p"):
        result[f"{column}_holm"] = result.groupby(["sample", "measure"])[column].transform(_holm_adjust)
    return result


def summarize_main_rule(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    samples = {"all_events": events, "episode_first": events[events["episode_first"]]}
    for sample_name, sample in samples.items():
        scopes: list[tuple[str, pd.DataFrame]] = [("full", sample)]
        for era, start, end in ERA_BOUNDS:
            era_sample = sample.copy()
            if start is not None:
                era_sample = era_sample[era_sample["event_date"] >= start]
            if end is not None:
                era_sample = era_sample[era_sample["event_date"] <= end]
            scopes.append((era, era_sample))
        scopes.extend(
            [
                ("drop_at_least_4pct", sample[sample["event_return"] <= -0.04]),
                ("drop_at_least_5pct", sample[sample["event_return"] <= -0.05]),
            ]
        )
        for scope, scoped_sample in scopes:
            for horizon in HORIZONS:
                outcome = f"return_{horizon}d"
                columns = [
                    "rebound_ratio",
                    outcome,
                    f"min_return_{horizon}d",
                    f"precrash_recovered_{horizon}d",
                ]
                eligible = scoped_sample[columns].dropna()
                for group, mask in (
                    ("recovered_at_least_half", eligible["rebound_ratio"] >= 0.5),
                    ("recovered_less_than_half", eligible["rebound_ratio"] < 0.5),
                ):
                    group_rows = eligible.loc[mask]
                    values = group_rows[outcome]
                    rows.append(
                        {
                            "sample": sample_name,
                            "scope": scope,
                            "horizon_days": horizon,
                            "group": group,
                            "n": len(values),
                            "median_return": values.median(),
                            "mean_return": values.mean(),
                            "positive_rate": (values > 0).mean(),
                            "median_min_return": group_rows[f"min_return_{horizon}d"].median(),
                            "precrash_recovery_rate": group_rows[
                                f"precrash_recovered_{horizon}d"
                            ].mean(),
                        }
                    )
    return pd.DataFrame(rows)


def compare_main_rule_scopes(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    samples = {"all_events": events, "episode_first": events[events["episode_first"]]}
    for sample_name, sample in samples.items():
        scopes: list[tuple[str, pd.DataFrame]] = [("full", sample)]
        for era, start, end in ERA_BOUNDS:
            era_sample = sample.copy()
            if start is not None:
                era_sample = era_sample[era_sample["event_date"] >= start]
            if end is not None:
                era_sample = era_sample[era_sample["event_date"] <= end]
            scopes.append((era, era_sample))
        scopes.extend(
            [
                ("drop_at_least_4pct", sample[sample["event_return"] <= -0.04]),
                ("drop_at_least_5pct", sample[sample["event_return"] <= -0.05]),
            ]
        )
        for scope, scoped_sample in scopes:
            for horizon in HORIZONS:
                outcome = f"return_{horizon}d"
                eligible = scoped_sample[["rebound_ratio", outcome]].dropna()
                high = eligible.loc[eligible["rebound_ratio"] >= 0.5, outcome]
                low = eligible.loc[eligible["rebound_ratio"] < 0.5, outcome]
                if high.empty or low.empty:
                    continue
                rows.append(
                    {
                        "sample": sample_name,
                        "scope": scope,
                        "horizon_days": horizon,
                        "high_n": len(high),
                        "low_n": len(low),
                        "median_return_difference": high.median() - low.median(),
                        "positive_rate_difference": (high > 0).mean() - (low > 0).mean(),
                        "mann_whitney_p": stats.mannwhitneyu(
                            high, low, alternative="two-sided"
                        ).pvalue,
                        "fisher_p": stats.fisher_exact(
                            [
                                [(high > 0).sum(), (high <= 0).sum()],
                                [(low > 0).sum(), (low <= 0).sum()],
                            ]
                        ).pvalue,
                    }
                )
    result = pd.DataFrame(rows)
    for column in ("mann_whitney_p", "fisher_p"):
        result[f"{column}_holm"] = result.groupby("sample")[column].transform(_holm_adjust)
    return result


def correlation_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for sample_name, sample in (
        ("all_events", events),
        ("episode_first", events[events["episode_first"]]),
    ):
        for horizon in HORIZONS:
            eligible = sample[["rebound_ratio", f"return_{horizon}d"]].dropna()
            result = stats.spearmanr(eligible["rebound_ratio"], eligible[f"return_{horizon}d"])
            rows.append(
                {
                    "sample": sample_name,
                    "horizon_days": horizon,
                    "n": len(eligible),
                    "spearman_rho": result.statistic,
                    "p_value": result.pvalue,
                }
            )
    result = pd.DataFrame(rows)
    result["p_value_holm"] = result.groupby("sample")["p_value"].transform(_holm_adjust)
    return result


def main() -> int:
    args = parse_args()
    prices = load_ixic(args.input)
    events = build_events(prices)
    args.output.mkdir(parents=True, exist_ok=True)
    events.to_csv(args.output / "events.csv", index=False, float_format="%.10f", date_format="%Y-%m-%d")
    compare_thresholds(events).to_csv(
        args.output / "threshold-comparison.csv", index=False, float_format="%.10f"
    )
    summarize_main_rule(events).to_csv(
        args.output / "half-recovery-summary.csv", index=False, float_format="%.10f"
    )
    compare_main_rule_scopes(events).to_csv(
        args.output / "half-recovery-comparison.csv", index=False, float_format="%.10f"
    )
    correlation_summary(events).to_csv(
        args.output / "correlation-summary.csv", index=False, float_format="%.10f"
    )
    metadata = {
        "generated_through": prices.index[-1].date().isoformat(),
        "first_observation": prices.index[0].date().isoformat(),
        "crash_threshold": -0.03,
        "episode_cooldown_sessions": 20,
        "horizons_sessions": list(HORIZONS),
        "complete_crash_events": len(events),
        "episode_first_events": int(events["episode_first"].sum()),
        "ixic_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "forward_return_origin": "next-day close",
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
