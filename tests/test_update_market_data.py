from pathlib import Path

import pandas as pd
import pytest

from scripts.list_market_events import identify_downturns, load_event_labels
from scripts.update_market_data import (
    DataValidationError,
    OHLC,
    build_synthetic_tqqq,
    is_nasdaq_session,
    latest_settled_session,
    validate_ohlc,
    write_csvs,
)


def frame(rows, start="2010-01-04"):
    return pd.DataFrame(
        rows,
        columns=OHLC,
        index=pd.bdate_range(start, periods=len(rows), name="Date"),
        dtype=float,
    )


def test_synthetic_tqqq_tracks_three_times_qqq_close_return():
    qqq = frame(
        [
            [100, 102, 99, 100],
            [100, 103, 99, 102],
            [102, 104, 101, 103],
            [103, 106, 102, 105],
        ]
    )
    actual = qqq.iloc[2:].copy()
    actual.loc[:, :] = [[40, 42, 39, 41], [41, 44, 40, 43]]

    result = build_synthetic_tqqq(qqq, actual)

    synthetic_dates = qqq.index[1:2]
    qqq_return = qqq["Close"].pct_change().loc[synthetic_dates]
    synthetic_return = result["Close"].pct_change().loc[synthetic_dates]
    pd.testing.assert_series_equal(
        synthetic_return,
        3 * qqq_return,
        check_names=False,
        rtol=1e-12,
    )
    pd.testing.assert_frame_equal(result.loc[actual.index], actual)
    validate_ohlc(result, "TQQQ")


def test_missing_real_tqqq_session_is_rejected():
    qqq = frame([[100, 101, 99, 100]] * 5)
    actual = qqq.iloc[[2, 4]].copy()

    with pytest.raises(DataValidationError, match="missing real sessions"):
        build_synthetic_tqqq(qqq, actual)


@pytest.mark.parametrize(
    "rows, message",
    [
        ([[100, 99, 98, 100]], "invalid OHLC"),
        ([[100, 101, 99, 0]], "finite and positive"),
        ([[100, 101, float("nan"), 100]], "missing values"),
    ],
)
def test_invalid_ohlc_is_rejected(rows, message):
    with pytest.raises(DataValidationError, match=message):
        validate_ohlc(frame(rows), "TEST")


def test_nasdaq_calendar_normal_holiday_and_early_close_sessions():
    assert is_nasdaq_session(pd.Timestamp("2026-07-20"))
    assert not is_nasdaq_session(pd.Timestamp("2026-07-04"))
    assert not is_nasdaq_session(pd.Timestamp("2026-12-25"))
    assert is_nasdaq_session(pd.Timestamp("2026-11-27"))


def test_latest_settled_session_waits_two_hours_after_close():
    assert latest_settled_session(pd.Timestamp("2026-01-05 22:59:00Z")) == pd.Timestamp(
        "2026-01-02"
    )
    assert latest_settled_session(pd.Timestamp("2026-01-05 23:00:00Z")) == pd.Timestamp(
        "2026-01-05"
    )


def test_write_csvs_has_stable_schema(tmp_path: Path):
    data = {
        name: frame([[100, 101, 99, 100]])
        for name in ["IXIC", "QQQ", "TQQQ", "SPY"]
    }
    write_csvs(data, tmp_path)

    text = (tmp_path / "QQQ.csv").read_text()
    assert text.splitlines()[0] == "Date,Open,High,Low,Close"
    assert text.splitlines()[1].startswith("2010.01.04,")
    assert not list(tmp_path.glob("*.tmp"))


def test_market_event_correction_boundaries_and_recovery():
    close = pd.Series(
        [100, 90, 95, 100],
        index=pd.bdate_range("2020-01-02", periods=4),
        dtype=float,
    )

    event = identify_downturns(close)[0]

    assert event.classification == "correction"
    assert event.drawdown == pytest.approx(-0.10)
    assert event.end_date == close.index[3]
    assert event.representative_date == close.index[1]


def test_market_event_bear_market_ends_after_twenty_percent_rebound():
    close = pd.Series(
        [100, 80, 79, 94.8],
        index=pd.bdate_range("2020-01-02", periods=4),
        dtype=float,
    )

    event = identify_downturns(close)[0]

    assert event.classification == "bear_market"
    assert event.drawdown == pytest.approx(-0.21)
    assert event.end_date == close.index[3]


def test_market_event_chart_labels_come_from_reviewed_document():
    document = Path(__file__).parents[1] / "docs" / "reference" / "market-events.md"

    labels = load_event_labels(document)

    assert labels["2020-03-16"] == "코로나19 충격"
    assert labels["2025-04-04"] == "상호관세 충격"
