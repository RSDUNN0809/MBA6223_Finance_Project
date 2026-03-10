"""
data.py — Intraday and daily data fetching via yfinance.

Key responsibilities:
  - Batch-download 1-minute intraday bars for a list of tickers
  - Fetch 30-day daily bars (for prev_close and avg_volume)
  - Extract the first 10 minutes of market-hours bars
  - Report current market status (pre / open / closed)
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from datetime import time as dtime
from typing import Optional

import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)

# How many worker threads for parallel single-ticker fetches (fallback path)
_MAX_WORKERS = 20


# ── Market status ─────────────────────────────────────────────────────────────

def market_status() -> str:
    """Return 'pre', 'open', or 'closed' based on current ET time."""
    now = datetime.now(ET)
    if now.weekday() >= 5:          # Saturday / Sunday
        return "closed"
    t = now.time()
    if t < MARKET_OPEN:
        return "pre"
    if t <= MARKET_CLOSE:
        return "open"
    return "closed"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_et(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the DataFrame index is timezone-aware and in US/Eastern."""
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET)
    return df


def _fetch_single_intraday(ticker: str) -> tuple[str, Optional[pd.DataFrame]]:
    """Fetch 1-min intraday bars for a single ticker (used as fallback)."""
    try:
        df = yf.Ticker(ticker).history(period="1d", interval="1m")
        if df.empty:
            return ticker, None
        return ticker, _to_et(df)
    except Exception as exc:
        logger.debug(f"Single fetch failed for {ticker}: {exc}")
        return ticker, None


# ── Public API ────────────────────────────────────────────────────────────────

def get_intraday_bars(
    tickers: list[str],
    batch_size: int = 200,
) -> dict[str, pd.DataFrame]:
    """
    Download 1-minute intraday bars for today for every ticker in *tickers*.

    Uses yfinance batch download (fast) and falls back to parallel single-ticker
    fetches if the batch path fails or returns empty data.

    Returns:
        dict mapping ticker -> DataFrame (OHLCV, ET-indexed)
    """
    all_data: dict[str, pd.DataFrame] = {}

    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start : batch_start + batch_size]

        try:
            if len(batch) == 1:
                raw = yf.download(
                    batch[0],
                    period="1d",
                    interval="1m",
                    auto_adjust=True,
                    progress=False,
                )
                if not raw.empty:
                    all_data[batch[0]] = _to_et(raw)
            else:
                raw = yf.download(
                    batch,
                    period="1d",
                    interval="1m",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )

                if raw.empty:
                    raise ValueError("Empty batch result")

                # columns is a MultiIndex: level-0 = ticker, level-1 = field
                available_tickers = raw.columns.get_level_values(0).unique().tolist()
                for ticker in available_tickers:
                    try:
                        df = raw[ticker].dropna(how="all")
                        if not df.empty:
                            all_data[ticker] = _to_et(df.copy())
                    except Exception as exc:
                        logger.debug(f"Extract failed for {ticker}: {exc}")

        except Exception as exc:
            logger.warning(
                f"Batch download failed (batch starting at {batch_start}): {exc}. "
                "Falling back to parallel single-ticker fetches."
            )
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                futures = {pool.submit(_fetch_single_intraday, t): t for t in batch}
                for future in as_completed(futures):
                    ticker, df = future.result()
                    if df is not None:
                        all_data[ticker] = df

    logger.info(f"Intraday bars fetched for {len(all_data)}/{len(tickers)} tickers.")
    return all_data


def get_daily_info(tickers: list[str], batch_size: int = 200) -> dict[str, dict]:
    """
    Fetch 30-day daily bars for every ticker and return per-ticker summary:
        prev_close  — closing price of the most recent completed session
        avg_volume  — mean daily volume over the 30-day window

    Returns:
        dict mapping ticker -> {"prev_close": float, "avg_volume": float}
    """
    result: dict[str, dict] = {}

    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start : batch_start + batch_size]
        try:
            if len(batch) == 1:
                raw = yf.download(
                    batch[0],
                    period="30d",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                )
                raw = raw.dropna(how="all")
                if len(raw) >= 2:
                    result[batch[0]] = {
                        "prev_close": float(raw["Close"].iloc[-2]),
                        "avg_volume": float(raw["Volume"].mean()),
                    }
            else:
                raw = yf.download(
                    batch,
                    period="30d",
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
                if raw.empty:
                    continue

                available_tickers = raw.columns.get_level_values(0).unique().tolist()
                for ticker in available_tickers:
                    try:
                        df = raw[ticker].dropna(how="all")
                        if len(df) >= 2:
                            result[ticker] = {
                                "prev_close": float(df["Close"].iloc[-2]),
                                "avg_volume": float(df["Volume"].mean()),
                            }
                    except Exception as exc:
                        logger.debug(f"Daily extract failed for {ticker}: {exc}")

        except Exception as exc:
            logger.warning(f"Daily batch download failed (batch {batch_start}): {exc}")

    logger.info(f"Daily info fetched for {len(result)}/{len(tickers)} tickers.")
    return result


def extract_first_10_min(bars: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Given a DataFrame of 1-min bars (ET-indexed), return the first 10 bars
    at or after 9:30 AM ET.  Returns None if there are no market-hours bars.
    """
    if bars is None or bars.empty:
        return None
    market_bars = bars[bars.index.time >= MARKET_OPEN]
    if market_bars.empty:
        return None
    return market_bars.head(10)
