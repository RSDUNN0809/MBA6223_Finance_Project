# CLAUDE.md — AI Assistant Guide for MBA6223 Finance Project

This file provides context, conventions, and workflows for AI coding assistants
(Claude Code and similar tools) working in this repository.

---

## Project Overview

**Course**: MBA6223 — Finance (Graduate-level)
**Application**: Morning 10-Minute Trading Signal Dashboard
**Language**: Python 3.11+
**UI**: Streamlit web app
**Data**: Yahoo Finance via `yfinance` (free, ~1-min delay)

Every morning the application fetches the first 10 minutes of trading data
(09:30–09:40 AM ET) for all S&P 500 constituents, scores each stock across
five technical indicators, and displays a colour-coded BUY / SELL / HOLD
signal table in the browser.

---

## Repository Structure

```
MBA6223_Finance_Project/
├── app.py               # Streamlit dashboard — entry point
├── requirements.txt     # Python dependencies
├── CLAUDE.md            # This file
└── src/
    ├── __init__.py
    ├── universe.py      # S&P 500 ticker list (Wikipedia → fallback)
    ├── data.py          # Intraday & daily data fetching (yfinance)
    └── signals.py       # Signal engine: indicators → BUY/SELL/HOLD
```

---

## Getting Started

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Launch the dashboard
streamlit run app.py
```

The app opens at http://localhost:8501.  Click **Refresh Data** in the sidebar
to trigger a new fetch.

---

## Module Reference

### `src/universe.py`

| Symbol | Description |
|--------|-------------|
| `get_sp500() -> pd.DataFrame` | Returns a DataFrame with columns `ticker`, `company`, `sector`. Scrapes Wikipedia; falls back to 20-stock hardcoded list on network failure. |

### `src/data.py`

| Symbol | Description |
|--------|-------------|
| `market_status() -> str` | Returns `"pre"`, `"open"`, or `"closed"` based on current ET time. |
| `get_intraday_bars(tickers, batch_size=200) -> dict[str, DataFrame]` | Batch-downloads 1-min bars for today via `yf.download()`. Falls back to parallel single-ticker fetches (20 threads) if the batch fails. |
| `get_daily_info(tickers, batch_size=200) -> dict[str, dict]` | Fetches 30-day daily bars; returns `prev_close` and `avg_volume` per ticker. |
| `extract_first_10_min(bars) -> DataFrame \| None` | Slices `bars` to the first 10 rows at or after 09:30 AM ET. |

### `src/signals.py`

| Symbol | Description |
|--------|-------------|
| `compute_signal(bars_10, prev_close, avg_daily_volume) -> dict` | Scores a single ticker. Returns `signal`, `score`, `votes`, `details`. |
| `assess_all(intraday_data, daily_info, universe) -> DataFrame` | Runs `compute_signal` for every ticker; returns tidy sorted DataFrame. |
| `BUY`, `SELL`, `HOLD` | String constants for signal values. |

### `app.py`

Streamlit entry point. Responsibilities:
- Sidebar: refresh button, signal filter, sector filter, methodology legend
- Cached `run_full_analysis()` (`ttl=300 s`) that calls `get_sp500 → get_intraday_bars → get_daily_info → assess_all`
- Summary metrics (BUY / SELL / HOLD counts)
- Plotly charts: signal pie, sector bar, score histogram
- Styled `st.dataframe` with colour-coded Signal and Score columns
- CSV download button

---

## Signal Logic

Five indicators each vote **+1** (bullish), **0** (neutral), or **−1** (bearish).

| # | Indicator | Bullish (+1) | Bearish (−1) |
|---|-----------|-------------|-------------|
| 1 | **Gap** | Open ≥ +1 % vs prev close | Open ≤ −1 % |
| 2 | **Momentum** | 10-min return ≥ +0.3 % | 10-min return ≤ −0.3 % |
| 3 | **VWAP** | Last price ≥ VWAP +0.1 % | Last price ≤ VWAP −0.1 % |
| 4 | **Volume** | Vol ratio ≥ 1.5× (confirms momentum dir) | Vol ratio ≤ 0.5× → neutral |
| 5 | **Trend** | ≥ 4 of last 5 bars close > open | ≥ 4 of last 5 bars close < open |

**Aggregate score**: sum of votes ∈ [−5, +5]
- Score ≥ **+2** → `BUY`
- Score ≤ **−2** → `SELL`
- Otherwise → `HOLD`

VWAP is computed as the cumulative volume-weighted average price over the
first-10-minute window: `VWAP = Σ(typical_price × volume) / Σ(volume)` where
`typical_price = (High + Low + Close) / 3`.

---

## Development Conventions

### General
- **Read files before editing** — never modify a file you haven't read.
- **Minimal scope** — only change what is necessary for the task.
- **No speculative features** — don't add error handling or abstractions not
  explicitly requested.

### Python Style
- Follow PEP 8. Use type hints on all function signatures.
- Prefer vectorised pandas/numpy operations over Python loops.
- Named constants for thresholds (e.g. `_BUY_THRESHOLD = 2`).
- Finance variable names must be self-documenting:
  `risk_free_rate` not `r`, `gap_pct` not `g`, `prev_close` not `pc`.

### Streamlit
- Keep all Streamlit calls in `app.py`; keep `src/` free of `import streamlit`.
- Use `@st.cache_data(ttl=...)` for expensive fetches. Clear with
  `st.cache_data.clear()` on manual refresh.
- Do **not** call `st.progress` or other widget functions inside cached
  functions — they will not render correctly.

### Data
- Raw data comes from Yahoo Finance; do not hard-code prices or returns.
- Log warnings (not exceptions) when a single ticker fails — the app should
  always complete even if some tickers have missing data.
- `None` / `NaN` in the output table is acceptable and is rendered as `—` in
  the dashboard.

### Financial Accuracy
- VWAP formula: `Σ(typical × volume) / Σ(volume)` — do not use simple average.
- Volume expected baseline: `avg_daily_volume × (10/390) × 1.5` (open premium).
- Do not conflate adjusted and unadjusted prices. `auto_adjust=True` is used
  throughout to return split-adjusted closes.

---

## Git Workflow

```bash
git push -u origin <branch>
```

Branch naming:
- `main` — stable only
- `claude/<session-id>` — AI-generated branches
- `feature/<description>` — human-authored features

Commit style: imperative, present tense, descriptive.

```
Add RSI indicator to morning signal engine
Fix VWAP calculation when volume is zero
Update sector bar chart to use stacked mode
```

---

## Running Tests

No tests exist yet. When adding tests, use `pytest`:

```bash
pytest tests/ -v
pytest --cov=src tests/
```

Unit test `compute_signal` with synthetic bar DataFrames; do not make live
network calls in tests (mock `yfinance` calls with `pytest-mock`).

---

## Key Files At-a-Glance

| File | Edit when you want to… |
|------|------------------------|
| `src/universe.py` | Change the stock universe or fallback list |
| `src/data.py` | Change data source, batch size, or timezone handling |
| `src/signals.py` | Add/remove indicators, change thresholds, adjust scoring |
| `app.py` | Change dashboard layout, filters, charts, or caching TTL |
| `requirements.txt` | Add/remove Python dependencies |
