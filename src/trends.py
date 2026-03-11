"""
trends.py — Google Trends data fetcher and feature extractor.

Fetches 3-month weekly Google Trends search interest for a single ticker
and derives normalised features consumed by the ML trend signal model.

Public API
----------
fetch_trends(ticker)         -> pd.Series | None   (weekly interest, 0-100)
get_price_history_3m(ticker) -> pd.DataFrame | None (daily OHLCV, 3 months)
compute_trend_features(series) -> dict              (level_ratio, slope_4w, …)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

_LOG = logging.getLogger(__name__)

_TIMEFRAME = "today 3-m"


# ── Google Trends ─────────────────────────────────────────────────────────────

def fetch_trends(ticker: str, timeframe: str = _TIMEFRAME) -> Optional[pd.Series]:
    """
    Fetch weekly Google Trends interest-over-time for *ticker* (US, English).

    Returns a Series indexed by date with interest values 0-100, or None on
    failure (network error, rate-limit, no data returned).
    """
    try:
        from pytrends.request import TrendReq  # lazy import — optional dep

        pytrends = TrendReq(hl="en-US", tz=300)   # tz=300 → ET (UTC-5)
        pytrends.build_payload([ticker], timeframe=timeframe, geo="US")
        df = pytrends.interest_over_time()

        if df is None or df.empty or ticker not in df.columns:
            _LOG.warning("No Google Trends data returned for %s.", ticker)
            return None

        series = df[ticker].astype(float)
        # Drop trailing partial week if present
        if "isPartial" in df.columns:
            series = series[~df["isPartial"]]

        return series

    except ImportError:
        _LOG.warning("pytrends not installed — Google Trends unavailable.")
        return None
    except Exception as exc:
        _LOG.warning("Google Trends fetch failed for %s: %s", ticker, exc)
        return None


# ── 3-month price history ─────────────────────────────────────────────────────

def get_price_history_3m(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch ~3 months of daily OHLCV data for *ticker* via yfinance.

    Returns a DataFrame with a DatetimeIndex, or None on failure.
    """
    try:
        df = yf.download(
            ticker,
            period="3mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        _LOG.warning("3-month price history fetch failed for %s: %s", ticker, exc)
        return None


# ── Feature extraction ────────────────────────────────────────────────────────

def compute_trend_features(series: Optional[pd.Series]) -> dict:
    """
    Derive ML-ready features from a weekly Google Trends Series.

    Features
    --------
    level_ratio   : current week / 3-month mean  (>1 → above-average interest)
    slope_4w      : OLS slope of last 4 weeks, normalised by mean
    acceleration  : (last-2-week avg − prior-2-week avg) / mean
    current_level : raw interest value for the latest week (0-100)
    """
    if series is None or len(series) < 4:
        return {
            "level_ratio":   1.0,
            "slope_4w":      0.0,
            "acceleration":  0.0,
            "current_level": 50.0,
        }

    mean_3m = float(series.mean())
    current = float(series.iloc[-1])
    denom   = mean_3m if mean_3m > 0 else 1.0

    level_ratio = current / denom

    # 4-week OLS slope
    recent  = series.iloc[-4:].values.astype(float)
    x       = np.arange(len(recent), dtype=float)
    slope_4w = float(np.polyfit(x, recent, 1)[0]) / denom

    # Acceleration: last 2 weeks vs prior 2 weeks
    last2  = float(recent[-2:].mean()) if len(recent) >= 2 else current
    prior2 = float(recent[-4:-2].mean()) if len(recent) >= 4 else current
    acceleration = (last2 - prior2) / denom

    return {
        "level_ratio":   round(level_ratio,  4),
        "slope_4w":      round(slope_4w,     4),
        "acceleration":  round(acceleration, 4),
        "current_level": round(current,      2),
    }
