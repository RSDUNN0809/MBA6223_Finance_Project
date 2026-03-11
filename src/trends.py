"""
trends.py — Google Trends data fetcher and feature extractor.

Fetches 3-month weekly Google Trends search interest for a single ticker
and derives normalised features consumed by the ML trend signal model.

Public API
----------
fetch_trends(ticker)               -> pd.Series | None   (weekly interest, 0-100)
get_price_history_3m(ticker)       -> pd.DataFrame | None (daily OHLCV, 3 months)
compute_trend_features(series)     -> dict              (level_ratio, slope_4w, …)
fetch_top_trending_queries(n)      -> list[str]         (top N US trending searches)
fetch_query_interest(query)        -> pd.Series | None  (weekly interest for a query)
match_tickers_to_query(query, universe) -> list[str]    (S&P 500 tickers related to query)
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


# ── Real-time trending queries ─────────────────────────────────────────────────

def fetch_top_trending_queries(n: int = 3) -> list[str]:
    """
    Fetch the top *n* currently trending Google search queries in the US.

    Uses pytrends ``trending_searches``.  Returns a list of query strings;
    returns an empty list on any failure (rate-limit, network, import error).
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=300)
        df = pytrends.trending_searches(pn="united_states")

        if df is None or df.empty:
            _LOG.warning("trending_searches returned no data.")
            return []

        return df.iloc[:n, 0].tolist()

    except ImportError:
        _LOG.warning("pytrends not installed — trending queries unavailable.")
        return []
    except Exception as exc:
        _LOG.warning("fetch_top_trending_queries failed: %s", exc)
        return []


def fetch_query_interest(query: str, timeframe: str = _TIMEFRAME) -> Optional[pd.Series]:
    """
    Fetch weekly Google Trends interest-over-time for an arbitrary search *query*.

    Behaves identically to ``fetch_trends`` but accepts any string (not just a
    ticker symbol).  Returns a Series indexed by date (values 0-100) or None.
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=300)
        pytrends.build_payload([query], timeframe=timeframe, geo="US")
        df = pytrends.interest_over_time()

        if df is None or df.empty or query not in df.columns:
            _LOG.warning("No Google Trends data for query '%s'.", query)
            return None

        series = df[query].astype(float)
        if "isPartial" in df.columns:
            series = series[~df["isPartial"]]

        return series

    except ImportError:
        _LOG.warning("pytrends not installed — query interest unavailable.")
        return None
    except Exception as exc:
        _LOG.warning("fetch_query_interest failed for '%s': %s", query, exc)
        return None


def match_tickers_to_query(query: str, universe: "pd.DataFrame") -> list[str]:
    """
    Return a list of S&P 500 tickers whose company name or ticker symbol appears
    in *query* (case-insensitive substring match).

    Parameters
    ----------
    query    : trending search string, e.g. "Apple earnings"
    universe : DataFrame with columns ``ticker`` and ``company``

    Returns at most 5 matches.
    """
    query_lower = query.lower()
    matched: list[str] = []

    for _, row in universe.iterrows():
        ticker: str  = str(row.get("ticker", "")).lower()
        company: str = str(row.get("company", "")).lower()

        # Ticker match: whole-word check (avoids "AI" matching "RAIN" etc.)
        if ticker and (
            f" {ticker} " in f" {query_lower} "
            or query_lower.startswith(ticker + " ")
            or query_lower.endswith(" " + ticker)
            or query_lower == ticker
        ):
            matched.append(str(row["ticker"]))
            continue

        # Company name: require the first word of the company to appear
        first_word = company.split()[0] if company.split() else ""
        if first_word and len(first_word) > 3 and first_word in query_lower:
            matched.append(str(row["ticker"]))

    return matched[:5]
