"""
app.py — Fisher College of Business · Morning Signal Dashboard
MBA6223 | The Ohio State University

Run with:
    streamlit run app.py

Three views:
  1. Market Overview  — overall market sentiment + top movers
  2. By Industry      — sector breakdown + filtered stock table
  3. Individual Stock — per-ticker signal detail with 10-min chart
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pytz
import streamlit as st

from src.data import (
    extract_first_10_min,
    get_daily_info,
    get_intraday_bars,
    market_status,
)
from src.signals import BUY, HOLD, SELL, assess_all, compute_signal
from src.universe import get_sp500

# ── Constants ─────────────────────────────────────────────────────────────────
ET = pytz.timezone("America/New_York")

OSU_SCARLET  = "#BB0000"
OSU_GRAY     = "#4F4F4F"
OSU_LIGHTGRAY= "#AFAFAF"
OSU_WHITE    = "#FFFFFF"

# Signal palette — kept distinct from OSU brand so they're universally legible
SIG_BUY_BG   = "#1a7a3a"   # dark green
SIG_SELL_BG  = "#a81c1c"   # dark red
SIG_HOLD_BG  = "#9c7a00"   # dark gold

SIG_COLORS = {BUY: "#2ecc71", SELL: "#e74c3c", HOLD: "#f39c12"}


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OSU Fisher · Morning Signal Dashboard",
    page_icon="🌰",          # Buckeye
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <style>
    /* Hide default Streamlit chrome */
    #MainMenu {{visibility:hidden;}}
    footer    {{visibility:hidden;}}

    /* Sidebar: dark scarlet gradient */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #1f0000 0%, #3a0000 100%);
        border-right: 3px solid {OSU_SCARLET};
    }}
    [data-testid="stSidebar"] * {{color: #f5f0f0 !important;}}
    [data-testid="stSidebar"] .stButton > button {{
        background: {OSU_SCARLET};
        color: white;
        border: none;
        font-weight: 600;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: #990000;
        color: white;
    }}
    [data-testid="stSidebar"] hr {{border-color: #660000;}}

    /* Metric cards */
    [data-testid="metric-container"] {{
        background: white;
        border-radius: 10px;
        padding: 14px 18px;
        border-top: 4px solid {OSU_SCARLET};
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}

    /* Tab selected indicator */
    [data-testid="stTabs"] button[aria-selected="true"] {{
        color: {OSU_SCARLET} !important;
        border-bottom: 3px solid {OSU_SCARLET};
    }}

    /* Scrollbar */
    ::-webkit-scrollbar       {{width:6px; height:6px;}}
    ::-webkit-scrollbar-thumb {{background:{OSU_SCARLET}; border-radius:3px;}}

    /* Signal badge helper classes (used inline) */
    .sig-buy  {{background:{SIG_BUY_BG};  color:white; padding:4px 12px; border-radius:6px; font-weight:700;}}
    .sig-sell {{background:{SIG_SELL_BG}; color:white; padding:4px 12px; border-radius:6px; font-weight:700;}}
    .sig-hold {{background:{SIG_HOLD_BG}; color:white; padding:4px 12px; border-radius:6px; font-weight:700;}}
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Fisher header banner ──────────────────────────────────────────────────────
def _fisher_banner(subtitle: str = "") -> None:
    now_et = datetime.now(ET)
    mkt     = market_status()
    mkt_label = {"pre": "🟡 PRE-MARKET", "open": "🟢 MARKET OPEN", "closed": "🔴 MARKET CLOSED"}
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {OSU_SCARLET} 0%, #8B0000 100%);
            color: white;
            padding: 22px 30px;
            border-radius: 12px;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 24px;
            box-shadow: 0 4px 16px rgba(187,0,0,0.25);
        ">
            <!-- Block-O wordmark -->
            <div style="
                font-size: 52px;
                font-weight: 900;
                line-height: 1;
                letter-spacing: -2px;
                border: 4px solid white;
                width: 72px;
                height: 72px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                flex-shrink: 0;
            ">O</div>

            <!-- Text block -->
            <div style="flex:1;">
                <div style="font-size:11px; letter-spacing:3px; opacity:0.85; text-transform:uppercase;">
                    The Ohio State University
                </div>
                <div style="font-size:26px; font-weight:700; letter-spacing:0.3px; margin:2px 0;">
                    Fisher College of Business
                </div>
                <div style="font-size:14px; opacity:0.85;">
                    MBA6223 &mdash; Morning 10-Minute Signal Dashboard
                    {"&nbsp;·&nbsp;" + subtitle if subtitle else ""}
                </div>
            </div>

            <!-- Market status + time -->
            <div style="text-align:right; flex-shrink:0;">
                <div style="font-size:15px; font-weight:600;">
                    {mkt_label.get(mkt, "⚪ UNKNOWN")}
                </div>
                <div style="font-size:13px; opacity:0.85; margin-top:4px;">
                    {now_et.strftime("%I:%M:%S %p ET")}
                </div>
                <div style="font-size:11px; opacity:0.7; margin-top:2px;">
                    {now_et.strftime("%A, %B %d %Y")}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Cached data functions ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def run_full_analysis() -> pd.DataFrame:
    universe = get_sp500()
    tickers  = universe["ticker"].tolist()
    intraday = get_intraday_bars(tickers)
    daily    = get_daily_info(tickers)
    return assess_all(intraday, daily, universe)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_detail(ticker: str) -> dict:
    """Full signal result + raw 10-min bars for a single ticker."""
    intraday  = get_intraday_bars([ticker])
    daily_map = get_daily_info([ticker])
    bars      = intraday.get(ticker)
    bars_10   = extract_first_10_min(bars)
    d         = daily_map.get(ticker, {})
    result    = compute_signal(
        bars_10,
        prev_close=d.get("prev_close"),
        avg_daily_volume=d.get("avg_volume"),
    )
    return {"bars_10": bars_10, "result": result, "daily": d}


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='text-align:center; padding:8px 0 4px;'>"
        "<span style='font-size:28px;'>🌰</span>"
        "<div style='font-size:16px; font-weight:700; letter-spacing:0.5px;'>OSU Fisher</div>"
        "<div style='font-size:11px; opacity:0.7;'>Morning Signal Dashboard</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    refresh_btn = st.button("🔄 Refresh Data", type="primary", use_container_width=True)

    st.divider()
    st.markdown("**Filter Signals**")
    filter_signals = st.multiselect(
        "Show signal types",
        options=[BUY, SELL, HOLD],
        default=[BUY, SELL, HOLD],
        label_visibility="collapsed",
    )

    st.markdown("**Filter by Industry**")
    sector_options: list[str] = st.session_state.get("sector_options", ["All Industries"])
    selected_sector = st.selectbox(
        "Industry",
        options=sector_options,
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown(
        """
**Signal Scoring**

Each indicator votes **+1 / 0 / −1**:

| | Indicator | Threshold |
|---|---|---|
| 1 | Gap vs close | ±1% |
| 2 | 10-min momentum | ±0.3% |
| 3 | VWAP position | ±0.1% |
| 4 | Volume vs expected | 1.5×/0.5× |
| 5 | Last-5-bar trend | ≥4 same |

**≥ +2 → BUY &nbsp;·&nbsp; ≤ −2 → SELL**
"""
    )


# ── Trigger analysis ──────────────────────────────────────────────────────────
if refresh_btn:
    st.cache_data.clear()
    for k in ["results", "last_updated", "sector_options"]:
        st.session_state.pop(k, None)

if "results" not in st.session_state:
    with st.status("Fetching S&P 500 first-10-min data…", expanded=True) as s:
        st.write("Downloading intraday bars — ~30–60 s for 500 stocks…")
        results_df = run_full_analysis()
        s.update(label="Analysis complete!", state="complete", expanded=False)

    st.session_state["results"]      = results_df
    st.session_state["last_updated"] = datetime.now(ET).strftime("%I:%M:%S %p ET")
    sectors = ["All Industries"] + sorted(results_df["Sector"].dropna().unique().tolist())
    st.session_state["sector_options"] = sectors

results_df: pd.DataFrame = st.session_state["results"]
last_updated: str         = st.session_state.get("last_updated", "—")

# Apply sidebar filters to the shared filtered view
display_df = results_df.copy()
if filter_signals:
    display_df = display_df[display_df["Signal"].isin(filter_signals)]
if selected_sector and selected_sector != "All Industries":
    display_df = display_df[display_df["Sector"] == selected_sector]


# ── Helper: styled signal table ───────────────────────────────────────────────
def _styled_table(df: pd.DataFrame) -> object:
    def _sig(v: str) -> str:
        return {
            BUY:  "background:#d4edda; color:#155724; font-weight:700",
            SELL: "background:#f8d7da; color:#721c24; font-weight:700",
            HOLD: "background:#fff3cd; color:#856404; font-weight:700",
        }.get(v, "")

    def _score(v: object) -> str:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ""
        if f >= 2:
            return "color:#155724; font-weight:700"
        if f <= -2:
            return "color:#721c24; font-weight:700"
        return ""

    fmt = {
        "Gap %":       "{:.2f}",
        "Momentum %":  "{:.2f}",
        "vs VWAP %":   "{:.3f}",
        "Vol Ratio":   "{:.2f}",
        "Last Price":  "{:.2f}",
        "VWAP":        "{:.2f}",
    }
    return (
        df.style
        .map(_sig,   subset=["Signal"])
        .map(_score, subset=["Score"])
        .format(fmt, na_rep="—")
    )


# ── Helper: overall sentiment label ──────────────────────────────────────────
def _market_sentiment(df: pd.DataFrame) -> tuple[str, str, str]:
    """Return (label, description, hex_color) for overall market recommendation."""
    n_buy  = int((df["Signal"] == BUY).sum())
    n_sell = int((df["Signal"] == SELL).sum())
    n_total = len(df)
    if n_total == 0:
        return "INSUFFICIENT DATA", "No signal data available.", OSU_GRAY

    buy_pct  = n_buy  / n_total * 100
    sell_pct = n_sell / n_total * 100
    net      = buy_pct - sell_pct

    if net >= 20:
        return "BROADLY BULLISH", f"{buy_pct:.0f}% BUY signals — strong broad-market buying pressure in the first 10 minutes.", "#1a7a3a"
    if net >= 8:
        return "MILDLY BULLISH", f"{buy_pct:.0f}% BUY vs {sell_pct:.0f}% SELL — cautiously positive open.", "#2e8b57"
    if net <= -20:
        return "BROADLY BEARISH", f"{sell_pct:.0f}% SELL signals — broad-market selling pressure at the open.", "#a81c1c"
    if net <= -8:
        return "MILDLY BEARISH", f"{sell_pct:.0f}% SELL vs {buy_pct:.0f}% BUY — cautiously negative open.", "#cc3333"
    return "NEUTRAL / MIXED", f"Balanced signals: {buy_pct:.0f}% BUY · {sell_pct:.0f}% SELL · {100-buy_pct-sell_pct:.0f}% HOLD.", OSU_GRAY


# ════════════════════════════════════════════════════════════════════════════
#  TABS
# ════════════════════════════════════════════════════════════════════════════
_fisher_banner()

tab_overview, tab_industry, tab_stock = st.tabs([
    "📊  Market Overview",
    "🏭  By Industry",
    "🔍  Individual Stock",
])


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 1 — MARKET OVERVIEW                                                │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_overview:

    st.caption(f"Last updated: {last_updated} &nbsp;·&nbsp; {len(results_df)} stocks analyzed")

    if mkt := market_status():
        if mkt == "pre":
            st.info("Market hasn't opened yet — signals reflect the most recent available bars.", icon="ℹ️")
        elif mkt == "closed":
            st.info("Market is closed — signals reflect the most recent session's first-10-min bars.", icon="ℹ️")

    # ── Overall Recommendation ─────────────────────────────────────────────
    sentiment, sentiment_desc, sentiment_color = _market_sentiment(results_df)

    n_buy   = int((results_df["Signal"] == BUY).sum())
    n_sell  = int((results_df["Signal"] == SELL).sum())
    n_hold  = int((results_df["Signal"] == HOLD).sum())
    n_total = len(results_df)

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {sentiment_color} 0%, {sentiment_color}cc 100%);
            color: white;
            padding: 28px 36px;
            border-radius: 14px;
            margin-bottom: 20px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.15);
        ">
            <div style="font-size:11px; letter-spacing:3px; text-transform:uppercase; opacity:0.85;">
                Overall Market Recommendation
            </div>
            <div style="font-size:36px; font-weight:800; letter-spacing:0.5px; margin:6px 0;">
                {sentiment}
            </div>
            <div style="font-size:15px; opacity:0.9; max-width:600px;">
                {sentiment_desc}
            </div>
            <div style="margin-top:16px; display:flex; gap:30px; font-size:14px; opacity:0.85;">
                <span>🟢 <strong>{n_buy}</strong> BUY ({n_buy/n_total*100:.0f}%)</span>
                <span>🔴 <strong>{n_sell}</strong> SELL ({n_sell/n_total*100:.0f}%)</span>
                <span>🟡 <strong>{n_hold}</strong> HOLD ({n_hold/n_total*100:.0f}%)</span>
                <span>📋 <strong>{n_total}</strong> total</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Metrics row ────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🟢 BUY",          n_buy,   help="Stocks with score ≥ +2")
    c2.metric("🔴 SELL",         n_sell,  help="Stocks with score ≤ −2")
    c3.metric("🟡 HOLD",         n_hold,  help="Stocks with score −1, 0, or +1")
    c4.metric("📋 Total Stocks",  n_total)
    c5.metric("⚠️ No Data",
              int(results_df["Last Price"].isna().sum()),
              help="Tickers with no intraday bars available")

    st.markdown("")

    # ── Charts ────────────────────────────────────────────────────────────
    ch1, ch2 = st.columns(2)

    with ch1:
        pie = px.pie(
            values=[n_buy, n_sell, n_hold],
            names=["BUY", "SELL", "HOLD"],
            color=["BUY", "SELL", "HOLD"],
            color_discrete_map=SIG_COLORS,
            title="<b>Signal Distribution — S&P 500</b>",
            hole=0.48,
        )
        pie.update_traces(textinfo="percent+label", textfont_size=13)
        pie.update_layout(
            legend=dict(orientation="h", y=-0.1),
            title_font=dict(size=15, color=OSU_GRAY),
        )
        st.plotly_chart(pie, use_container_width=True)

    with ch2:
        # Net signal per sector (BUY count − SELL count)
        sector_net = (
            results_df.groupby("Sector")
            .apply(
                lambda g: pd.Series({
                    "Net": int((g["Signal"] == BUY).sum()) - int((g["Signal"] == SELL).sum()),
                    "BUY":  int((g["Signal"] == BUY).sum()),
                    "SELL": int((g["Signal"] == SELL).sum()),
                })
            )
            .reset_index()
            .sort_values("Net", ascending=True)
        )
        colors = [SIG_COLORS[BUY] if v >= 0 else SIG_COLORS[SELL] for v in sector_net["Net"]]
        fig_net = go.Figure(go.Bar(
            x=sector_net["Net"],
            y=sector_net["Sector"],
            orientation="h",
            marker_color=colors,
            text=sector_net["Net"].apply(lambda x: f"+{x}" if x > 0 else str(x)),
            textposition="outside",
            customdata=sector_net[["BUY", "SELL"]].values,
            hovertemplate="<b>%{y}</b><br>Net: %{x}<br>BUY: %{customdata[0]} / SELL: %{customdata[1]}<extra></extra>",
        ))
        fig_net.update_layout(
            title="<b>Net Signal by Sector</b> (BUY − SELL)",
            title_font=dict(size=15, color=OSU_GRAY),
            xaxis_title="Net signal",
            margin=dict(l=0),
            height=400,
        )
        st.plotly_chart(fig_net, use_container_width=True)

    # ── Top movers ────────────────────────────────────────────────────────
    top_col, bot_col = st.columns(2)

    with top_col:
        st.markdown(
            f"<div style='background:{SIG_BUY_BG}; color:white; padding:8px 16px; "
            "border-radius:8px; font-weight:700; font-size:15px; margin-bottom:8px;'>"
            "🟢 Top 10 BUY Signals</div>",
            unsafe_allow_html=True,
        )
        top_buys = (
            results_df[results_df["Signal"] == BUY]
            .nlargest(10, "Score")[["Ticker", "Company", "Sector", "Score", "Momentum %", "Gap %", "Vol Ratio"]]
        )
        if top_buys.empty:
            st.info("No BUY signals yet.")
        else:
            st.dataframe(
                top_buys.style.format(
                    {"Momentum %": "{:.2f}", "Gap %": "{:.2f}", "Vol Ratio": "{:.2f}"},
                    na_rep="—",
                ),
                use_container_width=True,
                hide_index=True,
            )

    with bot_col:
        st.markdown(
            f"<div style='background:{SIG_SELL_BG}; color:white; padding:8px 16px; "
            "border-radius:8px; font-weight:700; font-size:15px; margin-bottom:8px;'>"
            "🔴 Top 10 SELL Signals</div>",
            unsafe_allow_html=True,
        )
        top_sells = (
            results_df[results_df["Signal"] == SELL]
            .nsmallest(10, "Score")[["Ticker", "Company", "Sector", "Score", "Momentum %", "Gap %", "Vol Ratio"]]
        )
        if top_sells.empty:
            st.info("No SELL signals yet.")
        else:
            st.dataframe(
                top_sells.style.format(
                    {"Momentum %": "{:.2f}", "Gap %": "{:.2f}", "Vol Ratio": "{:.2f}"},
                    na_rep="—",
                ),
                use_container_width=True,
                hide_index=True,
            )

    # ── Score distribution ─────────────────────────────────────────────────
    with st.expander("Score distribution histogram", expanded=False):
        hist = px.histogram(
            results_df,
            x="Score",
            color="Signal",
            color_discrete_map=SIG_COLORS,
            nbins=11,
            title="Distribution of Aggregate Indicator Scores (−5 to +5)",
            labels={"Score": "Aggregate score"},
        )
        hist.update_layout(bargap=0.1)
        st.plotly_chart(hist, use_container_width=True)


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 2 — BY INDUSTRY                                                    │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_industry:

    st.subheader("Industry Summary")
    st.caption("Net Signal = BUY count − SELL count within the industry. Positive is bullish.")

    # Sector summary table
    sector_summary = (
        results_df.groupby("Sector")
        .apply(
            lambda g: pd.Series({
                "# Stocks": len(g),
                "BUY":  int((g["Signal"] == BUY).sum()),
                "SELL": int((g["Signal"] == SELL).sum()),
                "HOLD": int((g["Signal"] == HOLD).sum()),
                "Net Signal": int((g["Signal"] == BUY).sum()) - int((g["Signal"] == SELL).sum()),
                "% Bullish": round((g["Signal"] == BUY).mean() * 100, 1),
                "Avg Score": round(g["Score"].mean(), 2),
            })
        )
        .reset_index()
        .sort_values("Net Signal", ascending=False)
    )

    def _net_color(v: object) -> str:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ""
        if f > 0:
            return "color:#155724; font-weight:700"
        if f < 0:
            return "color:#721c24; font-weight:700"
        return ""

    st.dataframe(
        sector_summary.style
        .map(_net_color, subset=["Net Signal"])
        .format({"% Bullish": "{:.1f}", "Avg Score": "{:.2f}"}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    st.divider()

    # Stacked bar by sector
    sector_counts = (
        results_df.groupby(["Sector", "Signal"])
        .size()
        .reset_index(name="Count")
    )
    fig_bar = px.bar(
        sector_counts,
        x="Sector",
        y="Count",
        color="Signal",
        color_discrete_map=SIG_COLORS,
        barmode="stack",
        title="<b>Signal Counts by Industry Sector</b>",
    )
    fig_bar.update_xaxes(tickangle=35)
    fig_bar.update_layout(legend_title_text="Signal", title_font=dict(size=15, color=OSU_GRAY))
    st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # Filtered stock table
    filter_label = f"{selected_sector}" if selected_sector != "All Industries" else "All Industries"
    sig_label    = ", ".join(filter_signals) if filter_signals else "none"
    st.subheader(f"Stock Table — {filter_label} · Signals: {sig_label} ({len(display_df)} stocks)")

    if display_df.empty:
        st.warning("No stocks match the current sidebar filters.")
    else:
        st.dataframe(_styled_table(display_df), use_container_width=True, height=560)

        csv = display_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download filtered table as CSV",
            data=csv,
            file_name=f"signals_{datetime.now(ET).strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 3 — INDIVIDUAL STOCK                                               │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_stock:

    st.subheader("Individual Stock Analysis")

    all_tickers = sorted(results_df["Ticker"].tolist())

    # Stock search: text input (type to filter) OR selectbox
    search_col, sel_col = st.columns([2, 3])
    with search_col:
        ticker_search = st.text_input(
            "Search ticker",
            placeholder="e.g. AAPL",
            max_chars=10,
        ).upper().strip()
    with sel_col:
        filtered_tickers = (
            [t for t in all_tickers if ticker_search in t]
            if ticker_search
            else all_tickers
        )
        selected_ticker: Optional[str] = st.selectbox(
            "Select ticker",
            options=filtered_tickers if filtered_tickers else all_tickers,
        )

    if not selected_ticker:
        st.info("Select a stock above to see its signal detail.")
        st.stop()

    # Quick summary row from the pre-computed results
    row = results_df[results_df["Ticker"] == selected_ticker]
    if not row.empty:
        row = row.iloc[0]
        quick_signal = row["Signal"]
        quick_score  = row["Score"]
        quick_company = row["Company"]
        quick_sector  = row["Sector"]
    else:
        quick_signal = quick_score = quick_company = quick_sector = "—"

    # ── Signal badge ──────────────────────────────────────────────────────
    badge_color = {BUY: SIG_BUY_BG, SELL: SIG_SELL_BG, HOLD: SIG_HOLD_BG}.get(quick_signal, OSU_GRAY)
    badge_emoji = {BUY: "🟢", SELL: "🔴", HOLD: "🟡"}.get(quick_signal, "⚪")

    st.markdown(
        f"""
        <div style="display:flex; gap:20px; align-items:stretch; margin-bottom:20px; flex-wrap:wrap;">

            <!-- Signal badge -->
            <div style="
                background: linear-gradient(135deg, {badge_color} 0%, {badge_color}bb 100%);
                color: white;
                padding: 24px 40px;
                border-radius: 14px;
                text-align: center;
                min-width: 220px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.15);
            ">
                <div style="font-size:11px; letter-spacing:3px; text-transform:uppercase; opacity:0.85;">
                    Signal
                </div>
                <div style="font-size:48px; font-weight:900; letter-spacing:1px; margin:6px 0;">
                    {badge_emoji} {quick_signal}
                </div>
                <div style="font-size:16px; opacity:0.9;">Score: {quick_score} / 5</div>
            </div>

            <!-- Stock info -->
            <div style="
                background: white;
                border-radius: 14px;
                padding: 20px 28px;
                flex: 1;
                border-left: 5px solid {OSU_SCARLET};
                box-shadow: 0 2px 8px rgba(0,0,0,0.07);
            ">
                <div style="font-size:28px; font-weight:800; color:{OSU_SCARLET};">{selected_ticker}</div>
                <div style="font-size:16px; color:{OSU_GRAY}; margin:2px 0;">{quick_company}</div>
                <div style="font-size:13px; color:{OSU_LIGHTGRAY};">{quick_sector}</div>
                <div style="margin-top:12px; font-size:13px; color:{OSU_GRAY};">
                    Last Price: <strong>${row["Last Price"]:.2f}</strong>
                    &nbsp;·&nbsp; VWAP: <strong>${row["VWAP"]:.2f}</strong>
                    &nbsp;·&nbsp; Gap: <strong>{row["Gap %"]:+.2f}%</strong>
                    &nbsp;·&nbsp; Momentum: <strong>{row["Momentum %"]:+.2f}%</strong>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Fetch full detail (per-indicator breakdown + raw bars) ────────────
    with st.spinner(f"Loading detail for {selected_ticker}…"):
        detail = fetch_stock_detail(selected_ticker)

    full_result = detail["result"]
    bars_10     = detail["bars_10"]
    votes       = full_result.get("votes", {})
    dets        = full_result.get("details", {})

    # ── Indicator scorecard ───────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:17px; font-weight:700; color:{OSU_SCARLET}; "
        "margin-bottom:8px;'>Indicator Breakdown</div>",
        unsafe_allow_html=True,
    )

    def _vote_badge(v: int) -> str:
        if v == 1:
            return f"<span style='background:{SIG_BUY_BG};color:white;padding:2px 10px;border-radius:5px;font-weight:700;'>+1 Bullish</span>"
        if v == -1:
            return f"<span style='background:{SIG_SELL_BG};color:white;padding:2px 10px;border-radius:5px;font-weight:700;'>−1 Bearish</span>"
        return f"<span style='background:{SIG_HOLD_BG};color:white;padding:2px 10px;border-radius:5px;font-weight:700;'>0 Neutral</span>"

    def _val(x: object, fmt: str = ".2f") -> str:
        if x is None:
            return "—"
        try:
            return format(float(x), fmt)
        except (TypeError, ValueError):
            return str(x)

    indicators = [
        ("Gap vs Prior Close",
         f"{_val(dets.get('gap_pct'), '+.2f')}%",
         "Opening price vs previous session's close. Threshold: ±1%.",
         votes.get("gap", 0)),
        ("10-Min Momentum",
         f"{_val(dets.get('momentum_pct'), '+.2f')}%",
         "Price return from first bar open to 10th-minute close. Threshold: ±0.3%.",
         votes.get("momentum", 0)),
        ("VWAP Position",
         f"{_val(dets.get('price_vs_vwap_pct'), '+.3f')}% vs VWAP",
         f"Last price ${_val(dets.get('last_price'), '.2f')} vs VWAP ${_val(dets.get('vwap'), '.2f')}. Threshold: ±0.1%.",
         votes.get("vwap", 0)),
        ("Volume vs Expected",
         f"{_val(dets.get('vol_ratio'), '.2f')}×",
         "First-10-min volume vs expected baseline (avg daily vol × 10/390 × 1.5). High volume confirms momentum.",
         votes.get("volume", 0)),
        ("Last-5-Bar Trend",
         f"{dets.get('trend_up_bars', '—')}↑ / {dets.get('trend_dn_bars', '—')}↓",
         "Count of bullish vs bearish candles in the final 5 bars. ≥4 same direction triggers a vote.",
         votes.get("trend", 0)),
    ]

    scorecard_html = f"""
    <table style="width:100%; border-collapse:collapse; font-size:14px; margin-bottom:16px;">
      <thead>
        <tr style="background:{OSU_SCARLET}; color:white;">
          <th style="padding:10px 14px; text-align:left;">#</th>
          <th style="padding:10px 14px; text-align:left;">Indicator</th>
          <th style="padding:10px 14px; text-align:left;">Value</th>
          <th style="padding:10px 14px; text-align:left;">Vote</th>
          <th style="padding:10px 14px; text-align:left;">Interpretation</th>
        </tr>
      </thead>
      <tbody>
    """
    for i, (name, val, interp, vote) in enumerate(indicators, 1):
        bg = "#fafafa" if i % 2 == 0 else "white"
        scorecard_html += f"""
        <tr style="background:{bg}; border-bottom:1px solid #eee;">
          <td style="padding:10px 14px; color:{OSU_LIGHTGRAY};">{i}</td>
          <td style="padding:10px 14px; font-weight:600;">{name}</td>
          <td style="padding:10px 14px; font-family:monospace;">{val}</td>
          <td style="padding:10px 14px;">{_vote_badge(vote)}</td>
          <td style="padding:10px 14px; color:{OSU_GRAY}; font-size:13px;">{interp}</td>
        </tr>
        """
    total_score = full_result.get("score", 0)
    scorecard_html += f"""
      </tbody>
      <tfoot>
        <tr style="background:#f0ecec; border-top:2px solid {OSU_SCARLET};">
          <td colspan="3" style="padding:12px 14px; font-weight:700; font-size:15px;">
            Total Score
          </td>
          <td style="padding:12px 14px;">
            <span style="background:{badge_color}; color:white; padding:4px 16px;
                         border-radius:6px; font-weight:700; font-size:15px;">
              {'+' if total_score > 0 else ''}{total_score} → {quick_signal}
            </span>
          </td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    """
    st.markdown(scorecard_html, unsafe_allow_html=True)

    # ── 10-minute price chart ─────────────────────────────────────────────
    if bars_10 is not None and not bars_10.empty:
        st.markdown(
            f"<div style='font-size:17px; font-weight:700; color:{OSU_SCARLET}; "
            "margin-bottom:8px;'>First 10-Minute Price Chart</div>",
            unsafe_allow_html=True,
        )

        vwap_val = dets.get("vwap")

        fig = go.Figure()

        # Candlestick bars
        fig.add_trace(go.Candlestick(
            x=bars_10.index.strftime("%H:%M"),
            open=bars_10["Open"],
            high=bars_10["High"],
            low=bars_10["Low"],
            close=bars_10["Close"],
            name=selected_ticker,
            increasing_line_color=SIG_COLORS[BUY],
            decreasing_line_color=SIG_COLORS[SELL],
        ))

        # VWAP line
        if vwap_val:
            fig.add_hline(
                y=vwap_val,
                line_dash="dash",
                line_color=OSU_SCARLET,
                line_width=2,
                annotation_text=f"VWAP ${vwap_val:.2f}",
                annotation_position="right",
                annotation_font_color=OSU_SCARLET,
            )

        # Volume bars on secondary y-axis
        vol_colors = [
            SIG_COLORS[BUY] if c >= o else SIG_COLORS[SELL]
            for c, o in zip(bars_10["Close"], bars_10["Open"])
        ]
        fig.add_trace(go.Bar(
            x=bars_10.index.strftime("%H:%M"),
            y=bars_10["Volume"],
            name="Volume",
            marker_color=vol_colors,
            opacity=0.4,
            yaxis="y2",
        ))

        fig.update_layout(
            title=f"<b>{selected_ticker}</b> — 1-min bars, 09:30–09:40 ET",
            title_font=dict(size=15, color=OSU_GRAY),
            xaxis_rangeslider_visible=False,
            xaxis_title="Time (ET)",
            yaxis_title="Price ($)",
            yaxis2=dict(
                title="Volume",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            legend=dict(orientation="h", y=-0.15),
            height=420,
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No intraday bar data available for {selected_ticker}. This is normal outside market hours.")

    # ── Context: same-sector peers ─────────────────────────────────────────
    if quick_sector and quick_sector != "—":
        with st.expander(f"Peer signals in {quick_sector}", expanded=False):
            peers = (
                results_df[results_df["Sector"] == quick_sector]
                .sort_values("Score", ascending=False)
            )
            peers_highlight = peers.copy()
            st.dataframe(
                _styled_table(peers_highlight),
                use_container_width=True,
                height=380,
                hide_index=True,
            )


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    f"<div style='text-align:center; color:{OSU_LIGHTGRAY}; font-size:12px; padding:8px;'>"
    "Data via Yahoo Finance (yfinance) &nbsp;·&nbsp; "
    "First-10-minute window: 09:30–09:40 AM ET &nbsp;·&nbsp; "
    "Signals are informational only and do not constitute financial advice. &nbsp;·&nbsp; "
    f"Fisher College of Business &nbsp;·&nbsp; MBA6223"
    "</div>",
    unsafe_allow_html=True,
)
