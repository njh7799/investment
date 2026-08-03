#!/usr/bin/env python3
"""List reproducible SPY correction and bear-market episodes for chart annotations."""

from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Downturn:
    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    end_date: pd.Timestamp | None
    classification: str
    drawdown: float
    representative_date: pd.Timestamp
    representative_return: float


def load_event_labels(document: Path) -> dict[str, str]:
    """Read representative dates and labels from the reviewed Markdown table."""
    labels: dict[str, str] = {}
    for line in document.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7 or not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", cells[0]):
            continue
        date = pd.Timestamp(cells[0].replace(".", "-")).date().isoformat()
        labels[date] = cells[6]
    return labels


def identify_downturns(close: pd.Series) -> list[Downturn]:
    """Identify 10% corrections and 20% bear markets without overlapping regimes."""
    if close.empty:
        return []
    if not close.index.is_monotonic_increasing or close.index.has_duplicates:
        raise ValueError("close dates must be sorted and unique")
    if close.isna().any() or (close <= 0).any():
        raise ValueError("close prices must be positive and complete")

    phase = "bull"
    peak_date = close.index[0]
    peak = float(close.iloc[0])
    episode: dict[str, object] | None = None
    raw: list[dict[str, object]] = []

    for date, value_raw in close.items():
        value = float(value_raw)
        if phase == "bull":
            if value >= peak:
                peak = value
                peak_date = date
            if value <= peak * 0.90:
                phase = "correction"
                episode = {
                    "peak": peak,
                    "peak_date": peak_date,
                    "trough": value,
                    "trough_date": date,
                    "classification": "correction",
                }
            continue

        assert episode is not None
        if value < float(episode["trough"]):
            episode["trough"] = value
            episode["trough_date"] = date

        if phase == "correction":
            if value <= float(episode["peak"]) * 0.80:
                phase = "bear_market"
                episode["classification"] = "bear_market"
            elif value >= float(episode["peak"]):
                episode["end_date"] = date
                raw.append(episode)
                episode = None
                phase = "bull"
                peak = value
                peak_date = date
        elif value >= float(episode["trough"]) * 1.20:
            episode["end_date"] = date
            raw.append(episode)
            episode = None
            phase = "bull"
            peak = value
            peak_date = date

    if episode is not None:
        episode["end_date"] = None
        raw.append(episode)

    result: list[Downturn] = []
    for item in raw:
        segment = close.loc[item["peak_date"] : item["trough_date"]]
        daily_return = segment.pct_change()
        representative_date = daily_return.idxmin()
        result.append(
            Downturn(
                peak_date=pd.Timestamp(item["peak_date"]),
                trough_date=pd.Timestamp(item["trough_date"]),
                end_date=(
                    pd.Timestamp(item["end_date"])
                    if item["end_date"] is not None
                    else None
                ),
                classification=str(item["classification"]),
                drawdown=float(item["trough"]) / float(item["peak"]) - 1,
                representative_date=representative_date,
                representative_return=float(daily_return.loc[representative_date]),
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("assets/SPY.csv"))
    parser.add_argument("--start", default="1999-03-10")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    frame = pd.read_csv(args.input, parse_dates=["Date"], date_format="%Y.%m.%d")
    close = frame.set_index("Date")["Close"].loc[args.start :]
    result = pd.DataFrame(asdict(item) for item in identify_downturns(close))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.output, index=False)
    else:
        print(result.to_csv(index=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
