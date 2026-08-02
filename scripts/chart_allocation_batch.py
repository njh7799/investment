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

from analyze_allocation_batch import COMMON_START, run

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/AppleGothic.ttf")
plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False


MODELS = {
    "tqqq_hold": ("TQQQ hold", "#2979FF"),
    "qqq_hold": ("QQQ hold", "#40C4FF"),
    "vo": ("VO", "#FF9100"),
    "gem": ("GEM", "#00C853"),
    "gtaa5": ("GTAA 5", "#D500F9"),
}
EVENTS = {
    "2018-02-08": "금리·변동성 충격",
    "2018-10-24": "기술주 실적 우려",
    "2019-05-13": "중국 보복관세",
    "2019-08-05": "미·중 환율전쟁",
    "2020-03-16": "코로나19 충격",
    "2020-06-11": "2차 유행 우려",
    "2020-09-03": "빅테크 급락",
    "2020-10-28": "코로나 재확산",
    "2021-02-25": "국채금리 급등",
    "2022-02-03": "Meta 실적 쇼크",
    "2022-03-07": "우크라이나 전쟁",
    "2022-05-05": "연준 긴축 공포",
    "2022-09-13": "CPI 예상 상회",
    "2022-12-15": "매파적 연준",
    "2024-07-24": "빅테크 실적 충격",
    "2024-08-05": "고용 쇼크·캐리 청산",
    "2024-12-18": "금리인하 축소",
    "2025-01-27": "DeepSeek 충격",
    "2025-04-03": "상호관세 충격",
    "2025-10-10": "대중 관세 위협",
    "2026-06-05": "고용 호조·금리 우려",
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
        "2007-2011": (COMMON_START, "2011-12-31"),
    }


def main() -> int:
    output = ROOT / "results" / "research" / "charts" / "batch-03"
    output.mkdir(parents=True, exist_ok=True)
    for slug, (start, end) in periods().items():
        fig, ax = plt.subplots(figsize=(16, 8))
        for model, (label, color) in MODELS.items():
            equity = run(model, start, end).equity
            normalized = equity / 100_000.0
            ax.plot(normalized.index, normalized, color=color, linewidth=0.5, label=label)
        event_number = 0
        for date_text, label in EVENTS.items():
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
