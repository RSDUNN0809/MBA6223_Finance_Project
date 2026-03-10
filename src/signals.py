"""
signals.py — Morning 10-minute signal engine.

Five independent indicators each cast a directional vote:
  +1 = bullish,  0 = neutral,  -1 = bearish

Aggregate score:
  >= +2  →  BUY
  <= -2  →  SELL
  else   →  HOLD

Indicators
----------
1. Gap           — opening gap vs. previous close  (threshold: ±1 %)
2. Momentum      — price change over first 10 min  (threshold: ±0.3 %)
3. VWAP          — last price vs. cumulative VWAP  (threshold: ±0.1 %)
4. Volume        — first-10-min volume vs. expected (threshold: 1.5×/0.5×)
5. Trend         — bar-by-bar direction of last 5 candles (≥ 4 of 5 same way)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .data import extract_first_10_min

logger = logging.getLogger(__name__)

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"

_BUY_THRESHOLD = 2
_SELL_THRESHOLD = -2

# The expected first-10-min volume as a fraction of daily volume.
# The open tends to be busier, so we apply a 1.5× intraday multiplier.
# 10 minutes / 390 minutes in a trading day × 1.5 (open premium)
_EXPECTED_FIRST10_FRAC = (10 / 390) * 1.5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vwap(bars: pd.DataFrame) -> float:
    """Cumulative VWAP over the supplied bars."""
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3.0
    total_vol = bars["Volume"].sum()
    if total_vol == 0:
        return float(bars["Close"].iloc[-1])
    return float((typical * bars["Volume"]).sum() / total_vol)


# ── Core signal function ──────────────────────────────────────────────────────

def compute_signal(
    bars_10: Optional[pd.DataFrame],
    prev_close: Optional[float] = None,
    avg_daily_volume: Optional[float] = None,
) -> dict:
    """
    Compute the BUY / SELL / HOLD signal from the first 10 minutes of trading.

    Parameters
    ----------
    bars_10 : DataFrame | None
        1-min OHLCV bars covering the first 10 minutes of the session.
    prev_close : float | None
        Adjusted closing price of the previous session (used for gap calc).
    avg_daily_volume : float | None
        30-day mean daily volume (used for volume anomaly detection).

    Returns
    -------
    dict with keys:
        signal   — "BUY" | "SELL" | "HOLD"
        score    — int in [-5, +5]
        votes    — dict of per-indicator votes
        details  — dict of human-readable computed values
    """
    if bars_10 is None or bars_10.empty:
        return {
            "signal": HOLD,
            "score": 0,
            "votes": {},
            "details": {"error": "no_data"},
        }

    votes: dict[str, int] = {}
    details: dict[str, object] = {}

    first_open = float(bars_10["Open"].iloc[0])
    last_close = float(bars_10["Close"].iloc[-1])

    # ── 1. Gap signal ─────────────────────────────────────────────────────────
    if prev_close and prev_close > 0:
        gap_pct = (first_open - prev_close) / prev_close * 100.0
        details["gap_pct"] = round(gap_pct, 2)
        if gap_pct >= 1.0:
            votes["gap"] = 1
        elif gap_pct <= -1.0:
            votes["gap"] = -1
        else:
            votes["gap"] = 0
    else:
        details["gap_pct"] = None
        votes["gap"] = 0

    # ── 2. Momentum signal ────────────────────────────────────────────────────
    if first_open > 0:
        momentum_pct = (last_close - first_open) / first_open * 100.0
    else:
        momentum_pct = 0.0
    details["momentum_pct"] = round(momentum_pct, 2)

    if momentum_pct >= 0.3:
        votes["momentum"] = 1
    elif momentum_pct <= -0.3:
        votes["momentum"] = -1
    else:
        votes["momentum"] = 0

    # ── 3. VWAP signal ────────────────────────────────────────────────────────
    vwap_val = _vwap(bars_10)
    details["vwap"] = round(vwap_val, 4)
    details["last_price"] = round(last_close, 4)

    if vwap_val > 0:
        price_vs_vwap_pct = (last_close - vwap_val) / vwap_val * 100.0
    else:
        price_vs_vwap_pct = 0.0
    details["price_vs_vwap_pct"] = round(price_vs_vwap_pct, 3)

    if price_vs_vwap_pct >= 0.1:
        votes["vwap"] = 1
    elif price_vs_vwap_pct <= -0.1:
        votes["vwap"] = -1
    else:
        votes["vwap"] = 0

    # ── 4. Volume signal ──────────────────────────────────────────────────────
    first_10_volume = float(bars_10["Volume"].sum())

    if avg_daily_volume and avg_daily_volume > 0:
        expected = avg_daily_volume * _EXPECTED_FIRST10_FRAC
        vol_ratio = first_10_volume / expected
        details["vol_ratio"] = round(vol_ratio, 2)

        # High volume confirms the prevailing momentum direction; low volume
        # gives no signal (price moves are less reliable on thin tape).
        if vol_ratio >= 1.5:
            votes["volume"] = votes.get("momentum", 0)   # amplify momentum dir
        elif vol_ratio <= 0.5:
            votes["volume"] = 0                           # thin tape — neutral
        else:
            votes["volume"] = 0
    else:
        details["vol_ratio"] = None
        votes["volume"] = 0

    # ── 5. Trend (last-5-bar consistency) ─────────────────────────────────────
    if len(bars_10) >= 5:
        last_5 = bars_10.tail(5)
        bar_returns = (last_5["Close"] - last_5["Open"]).values
        n_up = int((bar_returns > 0).sum())
        n_dn = int((bar_returns < 0).sum())
        details["trend_up_bars"] = n_up
        details["trend_dn_bars"] = n_dn

        if n_up >= 4:
            votes["trend"] = 1
        elif n_dn >= 4:
            votes["trend"] = -1
        else:
            votes["trend"] = 0
    else:
        details["trend_up_bars"] = None
        details["trend_dn_bars"] = None
        votes["trend"] = 0

    # ── Aggregate ─────────────────────────────────────────────────────────────
    total_score = sum(votes.values())

    if total_score >= _BUY_THRESHOLD:
        signal = BUY
    elif total_score <= _SELL_THRESHOLD:
        signal = SELL
    else:
        signal = HOLD

    return {
        "signal": signal,
        "score": total_score,
        "votes": votes,
        "details": details,
    }


# ── Batch assessment ──────────────────────────────────────────────────────────

def assess_all(
    intraday_data: dict[str, pd.DataFrame],
    daily_info: dict[str, dict],
    universe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Run compute_signal for every ticker in *universe* and return a tidy
    DataFrame sorted by signal priority (BUY first) then by score descending.

    Columns
    -------
    Ticker, Company, Sector, Signal, Score,
    Gap %, Momentum %, vs VWAP %, Vol Ratio,
    Last Price, VWAP, Trend (up/dn bars)
    """
    rows = []

    for _, row in universe.iterrows():
        ticker: str = row["ticker"]
        bars = intraday_data.get(ticker)
        bars_10 = extract_first_10_min(bars)
        daily = daily_info.get(ticker, {})

        result = compute_signal(
            bars_10,
            prev_close=daily.get("prev_close"),
            avg_daily_volume=daily.get("avg_volume"),
        )

        d = result["details"]
        rows.append(
            {
                "Ticker": ticker,
                "Company": row.get("company", ""),
                "Sector": row.get("sector", ""),
                "Signal": result["signal"],
                "Score": result["score"],
                "Gap %": d.get("gap_pct"),
                "Momentum %": d.get("momentum_pct"),
                "vs VWAP %": d.get("price_vs_vwap_pct"),
                "Vol Ratio": d.get("vol_ratio"),
                "Last Price": d.get("last_price"),
                "VWAP": d.get("vwap"),
                "Trend ↑": d.get("trend_up_bars"),
                "Trend ↓": d.get("trend_dn_bars"),
            }
        )

    df = pd.DataFrame(rows)

    # Sort: BUY → SELL → HOLD, then by score descending within each group
    _order = {BUY: 0, SELL: 1, HOLD: 2}
    df["_sort"] = df["Signal"].map(_order)
    df = (
        df.sort_values(["_sort", "Score"], ascending=[True, False])
        .drop(columns="_sort")
        .reset_index(drop=True)
    )

    return df
