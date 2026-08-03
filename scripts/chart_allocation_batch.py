#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyze_allocation_batch import run
from analyze_paa_batch import COMMON_START as PAA_COMMON_START, run as run_paa
from list_market_events import load_event_labels

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/AppleGothic.ttf")
plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False


MODELS = {
    "tqqq_hold": ("TQQQ hold", "#2979FF"),
    "qqq_hold": ("QQQ hold", "#40C4FF"),
    "vo": ("VO", "#FF9100"),
    "gem": ("GEM", "#00C853"),
    "gtaa5": ("GTAA 5", "#D500F9"),
    "paa2": ("PAA2", "#FF1744"),
}
def periods() -> dict[str, tuple[str, str]]:
    return {
        "2026-ytd": ("2026-01-01", "2026-07-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2024": ("2024-01-01", "2024-12-31"),
        "2023": ("2023-01-01", "2023-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2017-2021": ("2017-01-01", "2021-12-31"),
        "2012-2016": ("2012-01-01", "2016-12-31"),
        "2007-2011": (PAA_COMMON_START, "2011-12-31"),
    }


def main() -> int:
    output = ROOT / "results" / "research" / "charts" / "public-models"
    output.mkdir(parents=True, exist_ok=True)
    events = load_event_labels(ROOT / "docs" / "reference" / "market-events.md")
    for slug, (start, end) in periods().items():
        fig, ax = plt.subplots(figsize=(16, 8))
        for model, (label, color) in MODELS.items():
            equity = (run_paa if model == "paa2" else run)(model, start, end).equity
            normalized = equity / 100_000.0
            ax.plot(normalized.index, normalized, color=color, linewidth=0.5, label=label)
        event_number = 0
        for date_text, label in events.items():
            date = pd.Timestamp(date_text)
            if pd.Timestamp(start) <= date <= pd.Timestamp(end):
                ax.axvline(date, color="#78909C", linewidth=0.5, alpha=0.8, linestyle="--", zorder=0)
                ax.text(
                    date,
                    0.02 + 0.06 * (event_number % 3),
                    label,
                    rotation=90,
                    color="#78909C",
                    fontsize=6,
                    va="bottom",
                    transform=ax.get_xaxis_transform(),
                    clip_on=True,
                )
                event_number += 1
        ax.set_yscale("log")
        ax.set_title(f"Public-model comparison: {slug}")
        ax.set_ylabel("Growth of $100,000 (multiple, log scale)")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(False)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(output / f"allocation-{slug}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
