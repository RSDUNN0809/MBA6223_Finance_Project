"""
signal_handler/handler.py — Lambda handler for the read-path API endpoints.

Routes (dispatched from path/method in the event):
  GET /signals              → latest run results for all tickers
  GET /signals/export       → presigned S3 URL for the day's CSV
  GET /signals/{ticker}     → history for a specific ticker
"""
from __future__ import annotations

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
PRESIGNED_URL_EXPIRY_SECONDS = 900  # 15 minutes

_dynamodb = boto3.resource("dynamodb")
_s3_client = boto3.client("s3")
_table = _dynamodb.Table(SIGNALS_TABLE_NAME)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _today_et() -> str:
    """Return today's date in ET as YYYY-MM-DD (approximated via UTC-4)."""
    et_now = datetime.now(timezone(timedelta(hours=-4)))
    return et_now.strftime("%Y-%m-%d")


def _response(status_code: int, body: Any) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


# ── Route handlers ─────────────────────────────────────────────────────────────

def _get_signals(run_date: str) -> dict:
    """Fetch all signal results for *run_date* from DynamoDB."""
    results = []
    last_key = None

    while True:
        kwargs: dict = {
            "KeyConditionExpression": Key("run_date").eq(run_date),
            "Limit": 500,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        resp = _table.query(**kwargs)
        results.extend(resp.get("Items", []))

        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

    # Sort: BUY → SELL → HOLD, then score descending
    order = {"BUY": 0, "SELL": 1, "HOLD": 2}
    results.sort(key=lambda x: (order.get(x.get("signal", "HOLD"), 2), -int(x.get("score", 0))))

    return _response(200, {"run_date": run_date, "count": len(results), "items": results})


def _get_ticker_history(ticker: str) -> dict:
    """Fetch the last 30 days of signals for a single ticker via ByTicker GSI."""
    resp = _table.query(
        IndexName="ByTicker",
        KeyConditionExpression=Key("ticker").eq(ticker.upper()),
        ScanIndexForward=False,  # most recent first
        Limit=30,
    )
    items = resp.get("Items", [])
    return _response(200, {"ticker": ticker.upper(), "count": len(items), "items": items})


def _get_export_url(run_date: str) -> dict:
    """Generate a presigned URL for the CSV export in S3."""
    key = f"signal-results-exports/{run_date}/signals.csv"

    try:
        _s3_client.head_object(Bucket=RESULTS_BUCKET_NAME, Key=key)
    except _s3_client.exceptions.ClientError:
        return _response(404, {"error": f"No export found for {run_date}"})

    url = _s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": RESULTS_BUCKET_NAME, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return _response(200, {"url": url, "expires_in_seconds": PRESIGNED_URL_EXPIRY_SECONDS})


# ── Entry point ────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    logger.info("Event: %s", json.dumps(event))

    path: str = event.get("rawPath", event.get("path", ""))
    method: str = event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
    path_params: dict = event.get("pathParameters") or {}
    query_params: dict = event.get("queryStringParameters") or {}

    run_date = query_params.get("date", _today_et())

    try:
        if method == "GET" and path == "/signals/export":
            return _get_export_url(run_date)

        if method == "GET" and "ticker" in path_params:
            return _get_ticker_history(path_params["ticker"])

        if method == "GET" and path in ("/signals", "/signals/"):
            return _get_signals(run_date)

        return _response(404, {"error": "Route not found"})

    except Exception as exc:
        logger.exception("Unhandled error")
        return _response(500, {"error": str(exc)})
