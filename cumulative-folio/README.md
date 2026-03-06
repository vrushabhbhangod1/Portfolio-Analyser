# 📊 Cumulative Folio

A personal portfolio analytics dashboard built with Streamlit. Upload statements from multiple brokers and get a unified view of performance, risk metrics, holdings, and benchmark comparisons — all locally, no data leaving your machine.

---

## Features

- **Multi-broker support** — Fidelity (PDF), E\*TRADE (PDF), and Interactive Brokers (CSV Flex Query)
- **Consolidated view** — net portfolio value, deposits/withdrawals, realised & unrealised gains across all accounts
- **Monthly timeline** — month-by-month breakdown with cumulative unrealised gains
- **Risk metrics** — Sharpe ratio, Sortino ratio, max drawdown, volatility, win rate
- **Benchmark comparison** — compare against S&P 500, NASDAQ, and other indices via yfinance
- **Holdings snapshot** — most recent positions per account with unrealised P&L
- **Realised gains split** — short-term vs long-term, with IBKR using FIFO-based classification
- **Export** — download consolidated data as CSV or Excel

---

## Getting Started

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd cumulative-folio
python -m venv portfolio_env
source portfolio_env/bin/activate   # Windows: portfolio_env\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

### 3. Upload your statements

Use the sidebar to upload files — the app auto-detects the broker from the file content.

| Broker | Format | Notes |
|--------|--------|-------|
| Fidelity | PDF monthly statements | Supports brokerage, Roth IRA, Traditional IRA, HSA |
| E\*TRADE | PDF monthly statements | |
| IBKR | CSV Flex Query | See setup guide below |

---

## Supported Statement Formats

### Fidelity
Upload any number of monthly PDF statements. The app keeps only the most recent holdings snapshot per account to avoid double-counting.

Accounts detected automatically:
- Brokerage
- Roth IRA
- Traditional IRA
- Health Savings Account (HSA)

### E\*TRADE
Upload monthly PDF statements. Holdings are taken from the most recent statement per account.

### Interactive Brokers (IBKR)
IBKR requires a **Flex Query CSV export** for the best results. This gives monthly P&L, unrealised gains, and ST/LT realised gain splits.

---

## IBKR Flex Query Setup

Flex Queries let you export structured data directly from IBKR. Follow these steps to create the query this app expects.

### Step 1 — Go to Reports > Flex Queries

Log in to [IBKR Client Portal](https://www.interactivebrokers.com) and navigate to:

> **Reports → Flex Queries → Create**

![IBKR Reports Menu](docs/images/ibkr_reports_menu.png)

---

### Step 2 — Select "Portfolio Analyst" query type

Choose **Portfolio Analyst** as the query type, then set the date range and format.

![IBKR Query Type](docs/images/ibkr_query_type.png)

---

### Step 3 — Configure the sections

Enable the following sections in the Flex Query builder:

| Section | Purpose |
|---------|---------|
| **NAV** (Net Asset Value) | Monthly portfolio value — used for change in value |
| **Cash Report** (STFU) | Deposits, withdrawals, dividends, interest |
| **Transfers** (TRFR) | ACATS security transfers in from other brokers |
| **Trades** (TRNT) | Closed positions — used for realised gain classification |
| **FIFO Performance Summary** | ST/LT split per symbol — used to classify trades as short- or long-term |
| **Open Positions** | Current holdings snapshot |

![IBKR Section Selector](docs/images/ibkr_sections.png)

---

### Step 4 — Set the period to "Monthly" and format to CSV

Under **Delivery**, set:
- **Period**: Monthly (or custom date range)
- **Format**: CSV
- **Date Format**: yyyy-MM-dd

![IBKR Delivery Settings](docs/images/ibkr_delivery.png)

---

### Step 5 — Run and download

Run the query and download the CSV. Upload it directly into the app via the IBKR file input in the sidebar.

The expected filename format is: `Portfolio_Analysis_Monthly.csv` (or any `.csv` file in the IBKR upload field).

---

## Dashboard Tabs

| Tab | What you see |
|-----|-------------|
| 📊 Consolidated | Total portfolio value, net deposits, overall P&L, risk metrics |
| 📈 Timeline | Month-by-month table and chart, cumulative unrealised gains |
| 🏦 Individual Brokers | Per-broker breakdown with their own risk metrics |
| 📦 Holdings | Most recent positions across all accounts |
| 🎯 Benchmarks | Portfolio vs S&P 500 / NASDAQ / user-selected index |
| 💾 Export | Download as CSV or Excel |

---

## Key Metrics Explained

**Win Rate** — % of calendar months where the total portfolio had a positive return. A "win" is any month where ending value > starting value, regardless of trades made.

**Realised (ST) / (LT)** — Short-term gains (held < 1 year) and long-term gains (held ≥ 1 year). For IBKR, classification uses the FIFO Performance Summary section. For Fidelity, it uses transaction-level annotations from the statement.

**Cumulative Unrealised** — Running total of monthly unrealised gains per account. Represents the total mark-to-market gain built up over time, not just the current month's change.

**Change in Value** — Investment return only: excludes deposits, withdrawals, and security transfers. Equivalent to `(ending NAV − starting NAV) − net deposits − ACATS transfers`.

---

## Project Structure

```
cumulative-folio/
│
├── app.py                          # Streamlit entry point — all UI views and tabs
│
├── src/                            # Core application logic
│   ├── broker_parsers.py           # PDF/CSV parsers for Fidelity, E*TRADE, and IBKR
│   ├── portfolio_calculator.py     # Metrics aggregation and timeline builder
│   ├── period_detector.py          # Date range detection and period alignment
│   ├── risk_analysis.py            # Sharpe, Sortino, max drawdown, win rate
│   ├── benchmark_comparison.py     # yfinance benchmark fetching and comparison
│   └── chart_builder.py            # Plotly chart builders
│
├── tests/
│   └── test_broker_parsers.py      # CLI script to test parsers against local statement files
│
├── docs/
│   └── images/                     # Screenshots for README (IBKR Flex Query guide etc.)
│
├── statements/                     # Your statement files — gitignored, never committed
│   ├── fidelity/
│   ├── etrade/
│   └── ibkr/
│
├── requirements.txt
├── README.md
└── .gitignore
```

