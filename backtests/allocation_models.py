from __future__ import annotations

import pandas as pd


ALLOCATION_MODELS = {
    "gtaa5_buyhold": ("SPY", "EFA", "IEF", "VNQ", "DBC"),
    "gtaa5": ("SPY", "EFA", "IEF", "VNQ", "DBC"),
    "gem": ("SPY", "VEU", "AGG"),
    "stocks_bonds_60_40_buyhold": ("SPY", "IEF"),
    "permanent_25_buyhold": ("SPY", "IEF", "GLD"),
}

PAA_RISKY = ("SPY", "QQQ", "IWM", "EEM", "VGK", "EWJ", "IYR", "GSG", "GLD", "TLT", "HYG", "LQD")
PAA_DEFENSIVE = ("SHY", "IEF")


def _month_end_dates(close: pd.DataFrame) -> pd.DatetimeIndex:
    return close.groupby(close.index.to_period("M")).tail(1).index


def build_allocation_weights(model: str, closes: pd.DataFrame) -> pd.DataFrame:
    index = closes.index
    weights = pd.DataFrame(0.0, index=index, columns=closes.columns)
    if model == "gtaa5_buyhold":
        weights.loc[:, ["SPY", "EFA", "IEF", "VNQ", "DBC"]] = 0.20
        return weights
    if model == "stocks_bonds_60_40_buyhold":
        weights["SPY"] = 0.60
        weights["IEF"] = 0.40
        return weights
    if model == "permanent_25_buyhold":
        weights["SPY"] = 0.25
        weights["IEF"] = 0.25
        weights["GLD"] = 0.25
        return weights

    month_dates = _month_end_dates(closes)
    month_close = closes.loc[month_dates].copy()
    month_close.index = month_close.index.to_period("M")
    sparse = pd.DataFrame(0.0, index=month_dates, columns=closes.columns)
    if model == "paa_n12_buyhold":
        weights.loc[:, list(PAA_RISKY)] = 1.0 / len(PAA_RISKY)
        return weights
    if model == "paa2":
        momentum = month_close / month_close.rolling(13).mean() - 1.0
        for date, (_, row) in zip(month_dates, momentum.iterrows()):
            risky = row[list(PAA_RISKY)]
            if risky.isna().any() or row[list(PAA_DEFENSIVE)].isna().any():
                continue
            bad = int((risky <= 0.0).sum())
            defensive_fraction = min(1.0, bad / 6.0)
            safe = row[list(PAA_DEFENSIVE)].idxmax()
            sparse.loc[date, safe] = defensive_fraction
            if defensive_fraction < 1.0:
                top = list(risky[risky > 0.0].nlargest(6).index)
                for name in top:
                    sparse.loc[date, name] = (1.0 - defensive_fraction) / len(top)
    elif model == "gtaa5":
        names = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
        state = month_close[names] > month_close[names].rolling(10).mean()
        sparse.loc[:, names] = state.to_numpy(dtype=float) * 0.20
    elif model == "gem":
        momentum = month_close[["SPY", "VEU"]].pct_change(12)
        for date, (_, row) in zip(month_dates, momentum.iterrows()):
            if row.isna().any():
                continue
            winner = row.idxmax()
            sparse.loc[date, winner if row[winner] > 0.0 else "AGG"] = 1.0
    elif model not in {"paa2"}:
        raise KeyError(f"unknown allocation model: {model}")
    return sparse.reindex(index).ffill().fillna(0.0)
