"""
universe.py — S&P 500 constituent list.

Fetches ticker symbols, company names, and sectors from Wikipedia.
Falls back to a small hardcoded list if the network request fails.
"""
import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Hardcoded fallback: top 20 S&P 500 stocks by weight
_FALLBACK = [
    ("AAPL", "Apple Inc.", "Information Technology"),
    ("MSFT", "Microsoft Corp.", "Information Technology"),
    ("NVDA", "NVIDIA Corp.", "Information Technology"),
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    ("GOOGL", "Alphabet Inc. (Class A)", "Communication Services"),
    ("META", "Meta Platforms Inc.", "Communication Services"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary"),
    ("BRK-B", "Berkshire Hathaway Inc.", "Financials"),
    ("JPM", "JPMorgan Chase & Co.", "Financials"),
    ("V", "Visa Inc.", "Financials"),
    ("UNH", "UnitedHealth Group Inc.", "Health Care"),
    ("XOM", "Exxon Mobil Corp.", "Energy"),
    ("LLY", "Eli Lilly and Co.", "Health Care"),
    ("JNJ", "Johnson & Johnson", "Health Care"),
    ("MA", "Mastercard Inc.", "Financials"),
    ("AVGO", "Broadcom Inc.", "Information Technology"),
    ("PG", "Procter & Gamble Co.", "Consumer Staples"),
    ("HD", "Home Depot Inc.", "Consumer Discretionary"),
    ("MRK", "Merck & Co. Inc.", "Health Care"),
    ("COST", "Costco Wholesale Corp.", "Consumer Staples"),
]


def get_sp500() -> pd.DataFrame:
    """
    Return a DataFrame of S&P 500 constituents with columns:
        ticker, company, sector
    """
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url, attrs={"id": "constituents"})
        df = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
        df.columns = ["ticker", "company", "sector"]
        # Yahoo Finance uses '-' instead of '.' in tickers (e.g. BRK.B -> BRK-B)
        df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
        logger.info(f"Fetched {len(df)} S&P 500 tickers from Wikipedia.")
        return df.reset_index(drop=True)
    except Exception as exc:
        logger.warning(f"Wikipedia fetch failed ({exc}). Using fallback list of {len(_FALLBACK)} tickers.")
        return pd.DataFrame(_FALLBACK, columns=["ticker", "company", "sector"])
