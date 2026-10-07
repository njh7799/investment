#!/usr/bin/env python3
"""Audit calendar returns and the opportunity costs of default VO allocations.

This is descriptive attribution, not a proposed or optimized trading rule.
Episode boundaries and thresholds are fixed independently of their outcomes.
"""
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

from backtests import BacktestResult, build_target_weights, load_market_data, run_weight_strategy

ACTUAL_START = pd.Timestamp("2010-02-11")


def annual_returns(result: BacktestResult) -> pd.DataFrame:
    """Carry holdings across years and include the first purchase's commission."""
    rows = []
    previous = result.initial_cash
    for year, equity in result.equity.groupby(result.equity.index.year):
        last = float(equity.iloc[-1])
        rows.append(dict(year=year, start=equity.index[0], end=equity.index[-1],
                         start_equity=previous, end_equity=last, return_rate=last / previous - 1))
        previous = last
    return pd.DataFrame(rows)


def runs(mask: pd.Series) -> list[tuple[int, int]]:
    """Inclusive integer boundaries of nonoverlapping true runs."""
    active = np.flatnonzero(mask.to_numpy(dtype=bool))
    if not len(active):
        return []
    chunks = np.split(active, np.flatnonzero(np.diff(active) > 1) + 1)
    return [(int(chunk[0]), int(chunk[-1])) for chunk in chunks]


def endpoint(prices: pd.DataFrame, last: int) -> tuple[pd.Timestamp, str, float]:
    if last + 1 < len(prices):
        return prices.index[last + 1], "open_before_rebalance", float(prices.Open.iloc[last + 1])
    return prices.index[last], "close_data_end", float(prices.Close.iloc[last])


def reduced_episodes(prices: pd.DataFrame, result: BacktestResult,
                     features: pd.DataFrame, *, every_cut: bool = False) -> pd.DataFrame:
    """Compare each reduced-exposure run against keeping the pre-cut shares.

    Both paths start at the same pre-sale open equity. VO includes every fee
    inside the run; neither path includes the subsequent full-allocation trade.
    Keeping the shares is a local counterfactual, not a chained strategy.
    """
    rows = []
    positions = result.positions
    prices = prices.loc[positions.index]
    boundaries = runs(positions.TargetWeight < 1)
    if every_cut:
        boundaries = []
        for start in np.flatnonzero(positions.TargetWeight.diff().to_numpy() < 0):
            previous_target = positions.TargetWeight.iloc[start - 1]
            restored = np.flatnonzero(positions.TargetWeight.iloc[start:].to_numpy() >= previous_target)
            last = start + int(restored[0]) - 1 if len(restored) else len(positions) - 1
            boundaries.append((int(start), last))
    for start, last in boundaries:
        if start == 0:
            # There is no pre-cut invested position in a fresh-start portfolio.
            continue
        before = positions.iloc[start - 1]
        date = prices.index[start]
        end_date, end_mark, end_price = endpoint(prices, last)
        base = float(before.Cash + before.Shares * prices.Open.iloc[start])
        final = positions.iloc[last]
        vo_return = float((final.Cash + final.Shares * end_price) / base - 1)
        kept_return = float((before.Cash + before.Shares * end_price) / base - 1)
        signal = features.loc[:date].iloc[-2]
        rows.append(dict(start=date, end=end_date, end_mark=end_mark, trading_days=last-start+1,
                         signal_date=features.loc[:date].index[-2],
                         entry_return30=float(signal.return30), entry_volatility=float(signal.volatility),
                         previous_weight=float(before.TargetWeight),
                         entry_weight=float(positions.TargetWeight.iloc[start]),
                         zero_weight_days=int((positions.TargetWeight.iloc[start:last+1] == 0).sum()),
                         tqqq_return=end_price / float(prices.Open.iloc[start]) - 1,
                         vo_return=vo_return, keep_shares_return=kept_return,
                         missed_return=kept_return-vo_return))
    return pd.DataFrame(rows)


def full_weight_drawdowns(prices: pd.DataFrame, result: BacktestResult,
                          features: pd.DataFrame) -> pd.DataFrame:
    """Peak-to-trough losses within full-target runs, reset on recovery/cut.

    Use entry open (after the entry fee), daily close, and exit open before
    selling. Do not use intraday highs/lows or count nested declines twice.
    """
    rows = []
    prices = prices.loc[result.positions.index]
    for start, last in runs(result.positions.TargetWeight == 1):
        pos = result.positions.iloc[start]
        entry = float(pos.Cash + pos.Shares * prices.Open.iloc[start])
        marks = [(prices.index[start], "open", entry)]
        marks += [(date, "close", float(result.equity.loc[date])) for date in prices.index[start:last+1]]
        end_date, end_mark, end_price = endpoint(prices, last)
        if end_mark == "open_before_rebalance":
            marks.append((end_date, end_mark, float(pos.Cash + pos.Shares * end_price)))
        peak = trough = marks[0]

        def append_event(recovery: pd.Timestamp | None) -> None:
            if trough[2] >= peak[2]:
                return
            trough_loc = features.index.get_loc(trough[0])
            prior = features.iloc[trough_loc - 1] if trough_loc else None
            rows.append(dict(regime_start=prices.index[start], peak=peak[0], peak_mark=peak[1],
                             trough=trough[0], trough_mark=trough[1],
                             vo_drawdown=trough[2] / peak[2] - 1,
                             recovery_within_full_weight=recovery, regime_end=end_date,
                             termination="recovered" if recovery is not None else end_mark,
                             trough_prior_volatility=np.nan if prior is None else float(prior.volatility),
                             trough_prior_return30=np.nan if prior is None else float(prior.return30),
                             trough_close_volatility=float(features.loc[trough[0], "volatility"])))

        for mark in marks[1:]:
            if mark[2] >= peak[2]:
                append_event(mark[0])
                peak = trough = mark
            elif mark[2] < trough[2]:
                trough = mark
        append_event(None)
    return pd.DataFrame(rows)


def falling_low_volatility_runs(prices: pd.DataFrame, result: BacktestResult,
                                features: pd.DataFrame) -> pd.DataFrame:
    """Already-falling, low-volatility states known before each holding day."""
    lagged = features.shift(1).reindex(result.positions.index)
    mask = ((lagged.return30 < 0) & (lagged.volatility <= .60)
            & (result.positions.TargetWeight == 1))
    prices = prices.loc[result.positions.index]
    rows = []
    for start, last in runs(mask):
        pos = result.positions.iloc[start]
        base = float(pos.Cash + pos.Shares * prices.Open.iloc[start])
        end_date, end_mark, end_price = endpoint(prices, last)
        final = result.positions.iloc[last]
        rows.append(dict(start=prices.index[start], end=end_date, end_mark=end_mark,
                         trading_days=last-start+1,
                         entry_return30=float(lagged.return30.iloc[start]),
                         entry_volatility=float(lagged.volatility.iloc[start]),
                         vo_return=float((final.Cash + final.Shares * end_price) / base - 1),
                         tqqq_return=end_price / float(prices.Open.iloc[start]) - 1))
    return pd.DataFrame(rows)


def analyze() -> dict[str, pd.DataFrame]:
    data = load_market_data(ROOT)
    prices, weights = build_target_weights("vo", data)
    features = pd.DataFrame(dict(return30=prices.Close.pct_change(30),
                                 volatility=prices.Close.pct_change().rolling(30).std(ddof=1)*np.sqrt(252)))
    collected: dict[str, list[pd.DataFrame]] = {
        name: [] for name in ("annual", "reduced", "cuts", "drawdowns", "falling", "summary")}
    for scope, start in (("full_with_synthetic", None), ("actual", ACTUAL_START)):
        vo = run_weight_strategy(prices, weights, start=start)
        annual = annual_returns(vo).rename(columns={"return_rate": "vo_return"})
        for model in ("tqqq_hold", "qqq_hold"):
            bp, bw = build_target_weights(model, data)
            bh = run_weight_strategy(bp, bw, start=start)
            annual[model + "_return"] = annual_returns(bh).return_rate.to_numpy()
        reduced = reduced_episodes(prices, vo, features)
        cuts = reduced_episodes(prices, vo, features, every_cut=True)
        drawdowns = full_weight_drawdowns(prices, vo, features)
        falling = falling_low_volatility_runs(prices, vo, features)
        positive = reduced.tqqq_return > 0
        up_entry = reduced.entry_return30 > 0
        summary = dict(scope=scope, start=vo.equity.index[0], end=vo.equity.index[-1],
                       sessions=len(vo.equity), reduced_episodes=len(reduced),
                       reduced_rising=int(positive.sum()),
                       up_entry_cuts=int(up_entry.sum()),
                       up_entry_rising=int((up_entry & positive).sum()),
                       reduced_losing=int((reduced.tqqq_return < 0).sum()),
                       cut_helped=int((reduced.missed_return < 0).sum()),
                       all_cuts=len(cuts),
                       all_up_entry_cuts=int((cuts.entry_return30 > 0).sum()),
                       falling_low_vol_runs=len(falling),
                       falling_low_vol_days=int(falling.trading_days.sum()),
                       falling_low_vol_losing=int((falling.vo_return < 0).sum()),
                       full_weight_days=int((vo.positions.TargetWeight == 1).sum()))
        for cutoff in (.01, .05, .10):
            tag = str(int(cutoff * 100))
            summary["rising_missed_ge_"+tag+"pp"] = int((positive & (reduced.missed_return >= cutoff)).sum())
            summary["up_entry_missed_ge_"+tag+"pp"] = int((positive & up_entry & (reduced.missed_return >= cutoff)).sum())
            summary["all_up_entry_cuts_missed_ge_"+tag+"pp"] = int(((cuts.entry_return30 > 0) & (cuts.tqqq_return > 0) & (cuts.missed_return >= cutoff)).sum())
            summary["falling_loss_ge_"+tag+"pct"] = int((falling.vo_return <= -cutoff).sum())
        for cutoff in (.05, .10, .20):
            summary["full_weight_dd_ge_"+str(int(cutoff*100))+"pct"] = int((drawdowns.vo_drawdown <= -cutoff).sum())
        collected["summary"].append(pd.DataFrame([summary]))
        for name, frame in (("annual", annual), ("reduced", reduced), ("cuts", cuts), ("drawdowns", drawdowns), ("falling", falling)):
            frame.insert(0, "scope", scope)
            collected[name].append(frame)
    return {key: pd.concat(frames, ignore_index=True) for key, frames in collected.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "vo-tradeoffs")
    args = parser.parse_args()
    tables = analyze()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(args.output / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    metadata = dict(
        generated_through=str(tables["annual"].end.max().date()),
        actual_tqqq_start=str(ACTUAL_START.date()), initial_cash=100_000, fee_rate=.001,
        cash_return=0, slippage=0, tax=0, integer_shares=True,
        annual_method="continuous holdings; prior year final close; initial cash in first year",
        price_basis="split/dividend adjusted OHLC; no separate dividend cash credit",
        reduced_episode="executed weight below 1 until next weight-1 open before trade; last close if unfinished",
        counterfactual="keep pre-cut shares/cash without trading to the same endpoint; local comparison only",
        individual_cuts="each downward transition until prior target restored; includes 50-to-0 cuts; overlapping events cannot be added",
        left_censoring="exclude initial reduced run without a preceding invested position",
        uptrend="trailing 30-session TQQQ close return > 0 on signal date",
        downtrend="trailing 30-session TQQQ close return < 0 on prior session",
        large_missed_return_pp=5, large_drawdown_pct=10,
        drawdown_marks="full-target entry post-fee open, daily closes, next cut pre-trade open; reset on recovery/cut",
        data_sha256={name: hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()
                     for name in ("TQQQ.csv", "QQQ.csv", "IXIC.csv")},
    )
    (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n")
    print(tables["summary"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
