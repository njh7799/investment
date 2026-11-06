import numpy as np
import pandas as pd
import pytest

from scripts.analyze_ixic_crash_rebound import build_events, load_ixic


def test_build_events_uses_next_day_close_as_forward_origin():
    dates = pd.bdate_range("2020-01-01", periods=9)
    closes = [100.0, 96.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0]
    prices = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes}, index=dates
    )

    events = build_events(prices)

    assert len(events) == 1
    event = events.iloc[0]
    assert event["event_date"] == dates[1]
    assert event["rebound_date"] == dates[2]
    assert np.isclose(event["event_return"], -0.04)
    assert np.isclose(event["next_day_return"], 98.0 / 96.0 - 1.0)
    assert np.isclose(event["rebound_ratio"], (98.0 / 96.0 - 1.0) / 0.04)
    assert np.isclose(event["exact_gap_recovery"], 0.5)
    assert np.isclose(event["return_5d"], 103.0 / 98.0 - 1.0)


def test_episode_first_requires_twenty_clear_sessions_since_previous_crash():
    dates = pd.bdate_range("2020-01-01", periods=30)
    closes = np.full(30, 100.0)
    closes[1:] = 96.0
    closes[3:] = 92.0
    closes[25:] = 88.0
    prices = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes}, index=dates
    )

    events = build_events(prices)

    assert events["event_date"].tolist() == [dates[1], dates[3], dates[25]]
    assert events["episode_first"].tolist() == [True, False, True]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.rename(columns={"Close": "Price"}), "unexpected IXIC columns"),
        (lambda frame: frame.assign(Date=["2020.01.02", "2020.01.02"]), "unique and increasing"),
        (lambda frame: frame.assign(Close=[100.0, np.nan]), "positive and complete"),
        (lambda frame: frame.assign(High=[99.0, 101.0]), "High violates"),
        (lambda frame: frame.assign(Low=[101.0, 99.0]), "Low violates"),
    ],
)
def test_load_ixic_rejects_invalid_schema_dates_and_ohlc(tmp_path, mutate, message):
    frame = pd.DataFrame(
        {
            "Date": ["2020.01.02", "2020.01.03"],
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 99.0],
            "Close": [100.0, 100.0],
        }
    )
    path = tmp_path / "IXIC.csv"
    mutate(frame).to_csv(path, index=False)

    with pytest.raises(ValueError, match=message):
        load_ixic(path)
