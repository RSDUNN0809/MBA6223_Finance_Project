"""
scheduler_handler/handler.py — Lambda handler for the morning analysis run.

Triggered by:
  - EventBridge Scheduler at 09:42 AM ET on weekdays
  - POST /signals/refresh (manual trigger via API)

Flow
----
1. Guard: abort if market is not open (handles the DST dual-schedule approach)
2. Fetch S&P 500 universe
3. Fetch intraday bars + daily info via yfinance
4. Run compute_signal for every ticker
5. Write results to DynamoDB (batch_writer, TTL = 30 days)
6. Write CSV export to S3
7. Return summary counts
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

SIGNALS_TABLE_NAME = os.environ["SIGNALS_TABLE_NAME"]
RESULTS_BUCKET_NAME = os.environ["RESULTS_BUCKET_NAME"]
SIGNAL_TTL_DAYS = int(os.environ.get("SIGNAL_TTL_DAYS", "30"))

_dynamodb = boto3.resource("dynamodb")
_s3_client = boto3.client("s3")
_table = _dynamodb.Table(SIGNALS_TABLE_NAME)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_et() -> datetime:
    return datetime.now(timezone(timedelta(hours=-4)))


def _is_market_open() -> bool:
    """Return True only during the 09:30–16:00 ET window on weekdays."""
    now = _now_et()
    if now.weekday() >= 5:
        return False
    t = now.time()
    from datetime import time as dtime
    return dtime(9, 29) <= t <= dtime(16, 1)


def _ttl_timestamp() -> int:
    """Unix epoch for SIGNAL_TTL_DAYS days from now (used as DynamoDB TTL)."""
    expiry = datetime.now(timezone.utc) + timedelta(days=SIGNAL_TTL_DAYS)
    return int(expiry.timestamp())


def _df_to_csv_bytes(df) -> bytes:
    """Serialise a pandas DataFrame to UTF-8 CSV bytes."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ── Entry point ────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    logger.info("Analysis triggered. Event source: %s", event.get("source", "api"))

    # ── Guard: only run when market is (or was just) open ─────────────────────
    if not _is_market_open():
        now_str = _now_et().isoformat()
        logger.info("Market not open at %s — skipping analysis.", now_str)
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "reason": "market_closed", "time_et": now_str})}

    run_date = _now_et().strftime("%Y-%m-%d")
    logger.info("Starting analysis for %s", run_date)

    # ── Import signal logic (available via Lambda Layer) ───────────────────────
    try:
        from src.universe import get_sp500
        from src.data import get_intraday_bars, get_daily_info
        from src.signals import assess_all
    except ImportError as exc:
        logger.error("Failed to import src modules from layer: %s", exc)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}

    # ── 1. Universe ────────────────────────────────────────────────────────────
    universe_df = get_sp500()
    tickers: list[str] = universe_df["ticker"].tolist()
    logger.info("Universe: %d tickers", len(tickers))

    # ── 2. Fetch data ──────────────────────────────────────────────────────────
    intraday_data = get_intraday_bars(tickers)
    daily_info = get_daily_info(tickers)

    # ── 3. Compute signals ─────────────────────────────────────────────────────
    results_df = assess_all(intraday_data, daily_info, universe_df)
    logger.info(
        "Signals computed: BUY=%d  SELL=%d  HOLD=%d",
        (results_df["Signal"] == "BUY").sum(),
        (results_df["Signal"] == "SELL").sum(),
        (results_df["Signal"] == "HOLD").sum(),
    )

    expires_at = _ttl_timestamp()
    computed_at = datetime.now(timezone.utc).isoformat()

    # ── 4. Write to DynamoDB ───────────────────────────────────────────────────
    with _table.batch_writer() as batch:
        for _, row in results_df.iterrows():
            item = {
                "run_date": run_date,
                "ticker": str(row["Ticker"]),
                "company": str(row.get("Company", "")),
                "sector": str(row.get("Sector", "")),
                "signal": str(row["Signal"]),
                "score": int(row["Score"]) if row["Score"] is not None else 0,
                "gap_pct": row.get("Gap %"),
                "momentum_pct": row.get("Momentum %"),
                "vs_vwap_pct": row.get("vs VWAP %"),
                "vol_ratio": row.get("Vol Ratio"),
                "last_price": row.get("Last Price"),
                "vwap": row.get("VWAP"),
                "trend_up": row.get("Trend ↑"),
                "trend_dn": row.get("Trend ↓"),
                "computed_at": computed_at,
                "expires_at": expires_at,
            }
            # Remove None values — DynamoDB rejects explicit nulls in batch writes
            item = {k: v for k, v in item.items() if v is not None}
            batch.put_item(Item=item)

    logger.info("DynamoDB write complete for %d tickers.", len(results_df))

    # ── 5. Write CSV to S3 ─────────────────────────────────────────────────────
    csv_key = f"signal-results-exports/{run_date}/signals.csv"
    _s3_client.put_object(
        Bucket=RESULTS_BUCKET_NAME,
        Key=csv_key,
        Body=_df_to_csv_bytes(results_df),
        ContentType="text/csv",
        Metadata={"run_date": run_date, "computed_at": computed_at},
    )
    logger.info("CSV exported to s3://%s/%s", RESULTS_BUCKET_NAME, csv_key)

    summary = {
        "run_date": run_date,
        "computed_at": computed_at,
        "total_tickers": len(results_df),
        "buy_count": int((results_df["Signal"] == "BUY").sum()),
        "sell_count": int((results_df["Signal"] == "SELL").sum()),
        "hold_count": int((results_df["Signal"] == "HOLD").sum()),
    }

    return {"statusCode": 200, "body": json.dumps(summary)}
