# SL Asset Analysis

Automated personal portfolio reporting for:
- CSE stock holdings (weekly)
- Unit trust holdings from Google Sheets + CAL NAV API (monthly)

## Project files

- `portfolio.py` — Weekly stock report generator
- `portfolio_monthly.py` — Monthly **unit trust only** report generator
- `generated/` — Output HTML reports (auto-created)

## What each script produces

### 1) Weekly stock report
Run:

```bash
python3 portfolio.py
```

Outputs:
- `generated/portfolio_report.html` (browser/interactive)
- `generated/portfolio_email.html` (email-safe HTML)

Behavior:
- Output filenames are fixed and overwrite previous versions each run.
- Stock data is fetched from TradingView scanner endpoints.

### 2) Monthly unit trust report
Run:

```bash
python3 portfolio_monthly.py
```

Output:
- `generated/monthly_portfolio_report.html`

Data sources:
- Transactions: shared Google Sheet export (XLSX)
- Latest NAVs: CAL Unit Trust API

Current monthly report sections:
- Executive summary cards (value, cost, unrealized/realized P&L, flow, est. month return)
- Portfolio health checks (missing NAV, stale NAV, matching quality)
- Allocation & contribution table
- Detailed holdings table
- Recent activity (current month)

## Prerequisites

- Python 3.9+
- Packages:
  - `requests`
  - `openpyxl`

Install:

```bash
pip install requests openpyxl
```

## Configuration

### Stocks (`portfolio.py`)
Update the `PORTFOLIO` list:
- `symbol`
- `units`
- `buy_price`

### Unit trusts (`portfolio_monthly.py`)
Update:
- `SHEET_ID` (Google Sheets document id)

Expected worksheet format (per tab):
- `Date`
- `Type`
- `Units`
- `Unit Price`
- `Total`

Notes:
- Tabs are mapped to CAL fund names using fuzzy matching.
- Cashflow sign is normalized using units/type rules to reduce input sign errors.

## Automation suggestion

- Run `portfolio.py` weekly (e.g., Sunday evening).
- Run `portfolio_monthly.py` once per month (e.g., last day or first day).

## Important notes

- This project is for personal tracking only, not financial advice.
- Generated files are intentionally excluded from Git (`generated/` in `.gitignore`).
- If you see a LibreSSL/OpenSSL warning from `urllib3` on macOS, report generation can still succeed.

## Repository

GitHub: https://github.com/kokilaw/sl-asset-analysis
