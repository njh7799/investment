"""Reusable backtesting primitives for documented investment strategies."""

from .core import BacktestResult, MarketData, load_market_data, run_weight_strategy
from .metrics import summarize
from .models import BATCHES, MODEL_SPECS, build_target_weights
from .documented import causal_reference_high, run_three_percent_rule, run_vr_5
from .portfolio import common_index, load_assets, run_portfolio_strategy
from .permanent import PERMANENT_ASSETS, permanent_band_trigger, run_permanent_portfolio
from .jordan import jordan_open_regimes, run_jordan_public_proxy, run_jordan_tqqq

__all__ = [
    "BacktestResult",
    "BATCHES",
    "MarketData",
    "MODEL_SPECS",
    "build_target_weights",
    "load_market_data",
    "run_weight_strategy",
    "summarize",
    "causal_reference_high",
    "run_three_percent_rule",
    "run_vr_5",
    "common_index",
    "load_assets",
    "run_portfolio_strategy",
    "PERMANENT_ASSETS",
    "permanent_band_trigger",
    "run_permanent_portfolio",
    "jordan_open_regimes",
    "run_jordan_public_proxy",
    "run_jordan_tqqq",
]
