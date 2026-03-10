# CLAUDE.md — AI Assistant Guide for MBA6223 Finance Project

This file provides context, conventions, and workflows for AI coding assistants (Claude Code and similar tools) working in this repository.

---

## Project Overview

**Course**: MBA6223 — Finance (Graduate-level)
**Repository**: MBA6223_Finance_Project
**Status**: Initial setup — project files are being added.

This project is an MBA-level finance coursework repository. It likely involves one or more of the following domains: financial modeling, portfolio analysis, valuation, risk management, quantitative methods, or data-driven finance. Update this section with the specific project description once defined.

---

## Repository Structure

```
MBA6223_Finance_Project/
├── CLAUDE.md            # This file — AI assistant guide
├── README.md            # Project overview (add when project is scoped)
├── data/                # Raw and processed financial datasets
├── notebooks/           # Jupyter notebooks for analysis
├── src/                 # Source code / scripts
├── reports/             # Generated reports, charts, outputs
├── tests/               # Unit and integration tests
└── requirements.txt     # Python dependencies (if Python-based)
```

> **Note**: This structure is a recommended convention. Update this section as the actual directory structure is established.

---

## Technology Stack

The project is not yet populated. Common stacks for MBA finance projects include:

### Python (most likely)
- **Data analysis**: `pandas`, `numpy`
- **Finance-specific**: `yfinance`, `quantlib`, `pyfolio`, `empyrical`, `zipline`
- **Visualization**: `matplotlib`, `seaborn`, `plotly`
- **Statistical modeling**: `statsmodels`, `scipy`
- **Machine learning (optional)**: `scikit-learn`
- **Notebooks**: `jupyter`

### R (alternative)
- `tidyverse`, `quantmod`, `PerformanceAnalytics`, `TTR`

Update this section once the actual stack is committed to the repository.

---

## Development Setup

### Initial Setup (Python)
```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Launch Jupyter notebooks (if applicable)
jupyter notebook
```

### Initial Setup (R)
```r
# Install required packages
install.packages(c("tidyverse", "quantmod", "PerformanceAnalytics"))
```

> Update this section once `requirements.txt` or equivalent dependency files exist.

---

## Running Tests

Once tests are added:
```bash
# Python (pytest)
pytest tests/

# With coverage
pytest --cov=src tests/
```

---

## Git Workflow

### Branch Strategy
- `main` — stable, reviewed code only
- `claude/<session-id>` — AI-generated branches (auto-created per Claude Code session)
- `feature/<description>` — human-authored feature branches

### Commit Conventions
Use clear, descriptive commit messages:
```
Add DCF valuation model for Project A
Fix CAPM beta calculation in portfolio module
Update data pipeline to pull from Yahoo Finance API
```

- Use present tense imperative style ("Add", "Fix", "Update")
- Reference data sources or model names where relevant
- Keep commits focused on a single logical change

### Pushing Changes
```bash
git push -u origin <branch-name>
```

---

## Key Conventions for AI Assistants

### General Principles
1. **Read before editing** — Always read existing files before modifying them.
2. **Minimal changes** — Only modify what is necessary for the task. Do not refactor unrelated code.
3. **No speculative features** — Do not add error handling, abstractions, or functionality not explicitly requested.
4. **Finance domain accuracy** — Verify that financial formulas, rates, and calculations are correct. Cite sources (e.g., CFA curriculum, textbook chapter) when implementing standard models.
5. **Data provenance** — Always document where financial data comes from (ticker, API, date range, source).

### Financial Modeling Conventions
- Use descriptive variable names that reflect financial concepts (`risk_free_rate`, `beta`, `market_premium`, not `r`, `b`, `mp`)
- Store magic numbers (e.g., trading days per year = 252, risk-free rate) as named constants
- Include units in variable names or comments where ambiguous (e.g., `price_usd`, `return_pct`)
- Clearly separate raw data, intermediate calculations, and final outputs

### Notebooks
- Each notebook should have a clear title cell and purpose statement
- Use markdown cells to explain methodology and assumptions
- Restart kernel and run all cells before committing (`Kernel > Restart & Run All`)
- Do not commit notebooks with large embedded data outputs — clear outputs before committing if output files are large

### Data Files
- Raw data belongs in `data/raw/` and should not be modified
- Processed/cleaned data belongs in `data/processed/`
- Do not commit large binary data files (>10MB) — use `.gitignore` or external storage
- Document data sources and retrieval dates in a `data/README.md` or inline comments

### Python Style
- Follow PEP 8 conventions
- Use type hints for function signatures where practical
- Keep functions focused and single-purpose
- Prefer `pandas` vectorized operations over Python loops for performance

---

## Common Tasks

### Adding a New Analysis
1. Create a new notebook in `notebooks/` or a script in `src/`
2. Document the financial question being answered at the top
3. State assumptions clearly (risk-free rate used, time period, etc.)
4. Validate results against known benchmarks where possible

### Updating Dependencies
```bash
pip freeze > requirements.txt
```

### Working with Financial Data
```python
import yfinance as yf

# Download historical prices
ticker = yf.Ticker("AAPL")
hist = ticker.history(period="5y")
```

---

## Important Notes for AI Assistants

- **This repository was analyzed on 2026-03-10** and contained no source files at that time. All structural recommendations above are conventions — verify against actual file contents before making changes.
- **Always check the actual directory structure** before assuming the layout described above is in place.
- **Finance calculations are high-stakes** in an academic context — double-check formulas and cite methodology.
- **Do not hallucinate data** — if financial data is needed, use real APIs (Yahoo Finance, FRED, etc.) or clearly label data as synthetic/example-only.
