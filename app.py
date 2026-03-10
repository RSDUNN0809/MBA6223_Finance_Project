"""
app.py — Morning 10-Minute Signal Dashboard (Streamlit)

Run with:
    streamlit run app.py

The dashboard fetches S&P 500 tickers, downloads the first 10 minutes of
intraday data, scores each stock across five technical indicators, and
displays a colour-coded BUY / SELL / HOLD table alongside summary charts.

Results are cached for 5 minutes so re-interactions don't re-trigger the
full data fetch.  Click "Refresh" to force a new fetch at any time.
"""
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

from src.data import get_daily_info, get_intraday_bars, market_status
from src.signals import BUY, HOLD, SELL, assess_all
from src.universe import get_sp500

ET = pytz.timezone("America/New_York")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Morning Signal Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Controls")

    refresh_btn = st.button("🔄 Refresh Data", type="primary", use_container_width=True)

    st.divider()

    filter_signals = st.multiselect(
        "Show signals",
        options=[BUY, SELL, HOLD],
        default=[BUY, SELL, HOLD],
    )

    # Sector filter populated after first fetch
    sector_options: list[str] = st.session_state.get("sector_options", ["All Sectors"])
    selected_sector = st.selectbox("Filter by Sector", options=sector_options)

    st.divider()
    st.markdown(
        """
**How signals are scored**

Each indicator votes **+1** (bullish) / **0** (neutral) / **−1** (bearish):

| # | Indicator | Threshold |
|---|-----------|-----------|
| 1 | **Gap** vs prev close | ±1 % |
| 2 | **Momentum** over 10 min | ±0.3 % |
| 3 | **VWAP** position | ±0.1 % |
| 4 | **Volume** vs expected | 1.5× / 0.5× |
| 5 | **Trend** (last 5 bars) | ≥4 same dir |

Score ≥ **+2** → 🟢 BUY
Score ≤ **−2** → 🔴 SELL
Otherwise → 🟡 HOLD
"""
    )


# ── Cached fetch + assess ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def run_full_analysis() -> pd.DataFrame:
    universe = get_sp500()
    tickers = universe["ticker"].tolist()
    intraday = get_intraday_bars(tickers)
    daily = get_daily_info(tickers)
    return assess_all(intraday, daily, universe)


# ── Trigger analysis ──────────────────────────────────────────────────────────

if refresh_btn:
    st.cache_data.clear()
    st.session_state.pop("results", None)

if "results" not in st.session_state or refresh_btn:
    status_placeholder = st.empty()
    with status_placeholder.status("Fetching S&P 500 first-10-min data…", expanded=True) as s:
        st.write("Downloading intraday bars (this takes ~30–60 s for 500 stocks)…")
        results_df = run_full_analysis()
        s.update(label="Analysis complete!", state="complete", expanded=False)
    status_placeholder.empty()

    st.session_state["results"] = results_df
    st.session_state["last_updated"] = datetime.now(ET).strftime("%I:%M:%S %p ET")
    # Populate sector filter options
    sectors = ["All Sectors"] + sorted(results_df["Sector"].dropna().unique().tolist())
    st.session_state["sector_options"] = sectors

results_df: pd.DataFrame = st.session_state["results"]
last_updated: str = st.session_state.get("last_updated", "—")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("📈 Morning 10-Minute Signal Dashboard")

now_et = datetime.now(ET)
mkt = market_status()
status_icon = {"pre": "🟡 PRE-MARKET", "open": "🟢 OPEN", "closed": "🔴 CLOSED"}

st.markdown(
    f"**Market**: {status_icon.get(mkt, '⚪ UNKNOWN')} &nbsp;|&nbsp; "
    f"**ET**: {now_et.strftime('%I:%M:%S %p, %b %d %Y')} &nbsp;|&nbsp; "
    f"**Last analysis**: {last_updated}"
)

if mkt == "pre":
    st.info(
        "Market hasn't opened yet. Signals shown are based on the most recent "
        "available 1-min bars — they may reflect yesterday's session.",
        icon="ℹ️",
    )
elif mkt == "closed":
    st.info(
        "Market is closed. Signals reflect the most recent session's first-10-min bars.",
        icon="ℹ️",
    )


# ── Apply filters ─────────────────────────────────────────────────────────────
display_df = results_df.copy()

if filter_signals:
    display_df = display_df[display_df["Signal"].isin(filter_signals)]

if selected_sector and selected_sector != "All Sectors":
    display_df = display_df[display_df["Sector"] == selected_sector]


# ── Summary metrics ───────────────────────────────────────────────────────────
n_buy = int((results_df["Signal"] == BUY).sum())
n_sell = int((results_df["Signal"] == SELL).sum())
n_hold = int((results_df["Signal"] == HOLD).sum())
n_total = len(results_df)
n_no_data = int(results_df["Last Price"].isna().sum())

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("🟢 BUY", n_buy)
col2.metric("🔴 SELL", n_sell)
col3.metric("🟡 HOLD", n_hold)
col4.metric("📋 Total", n_total)
col5.metric("⚠️ No data", n_no_data, help="Stocks with no intraday bars available")


# ── Charts ────────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    pie = px.pie(
        values=[n_buy, n_sell, n_hold],
        names=["BUY", "SELL", "HOLD"],
        color=["BUY", "SELL", "HOLD"],
        color_discrete_map={"BUY": "#28a745", "SELL": "#dc3545", "HOLD": "#ffc107"},
        title="Signal Distribution",
        hole=0.45,
    )
    pie.update_traces(textinfo="percent+label")
    st.plotly_chart(pie, use_container_width=True)

with chart_col2:
    sector_counts = (
        results_df.groupby(["Sector", "Signal"])
        .size()
        .reset_index(name="Count")
    )
    bar = px.bar(
        sector_counts,
        x="Sector",
        y="Count",
        color="Signal",
        color_discrete_map={"BUY": "#28a745", "SELL": "#dc3545", "HOLD": "#ffc107"},
        title="Signals by Sector",
        barmode="stack",
    )
    bar.update_xaxes(tickangle=35)
    bar.update_layout(legend_title_text="Signal")
    st.plotly_chart(bar, use_container_width=True)


# ── Score histogram ───────────────────────────────────────────────────────────
with st.expander("Score distribution", expanded=False):
    hist = px.histogram(
        results_df,
        x="Score",
        color="Signal",
        color_discrete_map={"BUY": "#28a745", "SELL": "#dc3545", "HOLD": "#ffc107"},
        nbins=11,
        title="Distribution of aggregate indicator scores (−5 to +5)",
        labels={"Score": "Aggregate score"},
    )
    hist.update_layout(bargap=0.1)
    st.plotly_chart(hist, use_container_width=True)


# ── Signal table ──────────────────────────────────────────────────────────────
st.subheader(f"Signal Table — {len(display_df)} stocks")

if display_df.empty:
    st.warning("No stocks match the current filters.")
else:
    # Colour the Signal column
    def _colour_signal(val: str) -> str:
        return {
            BUY: "background-color:#d4edda; color:#155724; font-weight:bold",
            SELL: "background-color:#f8d7da; color:#721c24; font-weight:bold",
            HOLD: "background-color:#fff3cd; color:#856404; font-weight:bold",
        }.get(val, "")

    # Colour Score column: green positive, red negative
    def _colour_score(val: object) -> str:
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        if v >= 2:
            return "color:#155724; font-weight:bold"
        if v <= -2:
            return "color:#721c24; font-weight:bold"
        return ""

    fmt = {
        "Gap %": "{:.2f}",
        "Momentum %": "{:.2f}",
        "vs VWAP %": "{:.3f}",
        "Vol Ratio": "{:.2f}",
        "Last Price": "{:.2f}",
        "VWAP": "{:.2f}",
    }

    styled = (
        display_df.style
        .map(_colour_signal, subset=["Signal"])
        .map(_colour_score, subset=["Score"])
        .format(fmt, na_rep="—")
    )

    st.dataframe(styled, use_container_width=True, height=620)

    # Download
    csv = display_df.to_csv(index=False)
    st.download_button(
        label="⬇️ Download filtered table as CSV",
        data=csv,
        file_name=f"signals_{datetime.now(ET).strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data via Yahoo Finance (yfinance). "
    "Signals are informational only and do not constitute financial advice. "
    "First-10-minute window: 09:30–09:40 AM ET."
)
