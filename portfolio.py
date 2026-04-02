#!/usr/bin/env python3
"""
CSE Portfolio Performance Reporter
Run: python3 portfolio.py
Generates a self-contained HTML report: portfolio_report_YYYY-MM-DD.html
"""

import requests
import json
from datetime import datetime, date, timezone
import os

# ─── Portfolio Configuration ──────────────────────────────────────────────────
# Update buy prices and units here as needed.
PORTFOLIO = [
    {"symbol": "CALT.N0000", "units": 1300, "buy_price": 10.00},
    {"symbol": "LMF.N0000",  "units": 600,  "buy_price": 54.71},
    {"symbol": "PARQ.N0000", "units": 380,  "buy_price": 66.64},
    {"symbol": "TKYO.N0000", "units": 465,  "buy_price": 77.46},
    {"symbol": "VFIN.N0000", "units": 305,  "buy_price": 79.88},
]

# ─── Unit Trust Configuration ─────────────────────────────────────────────────
# "fund_name" must match the "fundname" field from the CAL API exactly.
# buy_nav  = the NAV (sell price) at which you purchased.
# units    = number of units held.
UNIT_TRUSTS = [
    {"fund_name": "Capital Alliance High Yield Fund",          "units": 7976.48, "buy_nav": 45.2044},
    {"fund_name": "CAL Fixed Income Opportunities Fund",       "units": 5753.52, "buy_nav": 41.9121},
    {"fund_name": "Capital Alliance Quantitative Equity Fund", "units": 5464.91, "buy_nav": 65.4436},
]

CAL_UT_API = "https://cal.lk/wp-admin/admin-ajax.php?action=getUnitTrust"

TV_EXCHANGE = "CSELK"
TV_FIELDS = [
    "close", "open", "high", "low", "volume",
    "change_abs", "change",
    "price_52_week_high", "price_52_week_low",
    "Perf.W", "Perf.1M", "Perf.3M", "Perf.Y",
    "market_cap_basic",
]

# ─── Data Fetcher ──────────────────────────────────────────────────────────────

def fetch_quote(symbol: str) -> dict:
    """Fetch latest quote data from TradingView scanner API."""
    tv_symbol = f"{TV_EXCHANGE}:{symbol}"
    fields_str = "%2C".join(TV_FIELDS)
    url = (
        f"https://scanner.tradingview.com/symbol"
        f"?symbol={tv_symbol.replace(':', '%3A')}"
        f"&fields={fields_str}&no_404=true"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tradingview.com/",
        "Origin": "https://www.tradingview.com",
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_all_quotes(portfolio: list) -> list:
    """Fetch quotes for all portfolio stocks and attach market data."""
    results = []
    for stock in portfolio:
        symbol = stock["symbol"]
        print(f"  Fetching {symbol}...", end=" ", flush=True)
        try:
            data = fetch_quote(symbol)
            current_price = data.get("close")
            if current_price is None:
                raise ValueError("No price returned")
            results.append({**stock, "market": data, "error": None})
            print(f"LKR {current_price:.2f} ✓")
        except Exception as e:
            results.append({**stock, "market": {}, "error": str(e)})
            print(f"ERROR: {e}")
    return results


# ─── Calculator ────────────────────────────────────────────────────────────────

def calculate(stocks: list) -> list:
    """Add computed fields to each stock entry."""
    # First pass: core per-stock numbers (weight needs total_value, computed after)
    enriched = []
    for s in stocks:
        d = dict(s)
        if s["error"]:
            enriched.append(d)
            continue
        m = s["market"]
        cp    = m.get("close", 0)
        bp    = s["buy_price"]
        units = s["units"]
        perf_w = m.get("Perf.W")  # weekly % change of the stock price

        d["current_price"]    = cp
        d["cost_basis"]       = round(bp * units, 2)
        d["current_value"]    = round(cp * units, 2)
        d["pnl_lkr"]          = round((cp - bp) * units, 2)
        d["pnl_pct"]          = round(((cp - bp) / bp) * 100, 2) if bp else 0
        # Weekly LKR gain: reverse-engineer prior week close from Perf.W
        if perf_w is not None:
            prior_price         = cp / (1 + perf_w / 100)
            d["weekly_pnl_lkr"] = round((cp - prior_price) * units, 2)
        else:
            d["weekly_pnl_lkr"] = None
        d["week52_high"]      = m.get("price_52_week_high")
        d["week52_low"]       = m.get("price_52_week_low")
        # How far below the 52W high (negative = below peak)
        w52h = d["week52_high"]
        d["pct_from_52w_high"] = round((cp - w52h) / w52h * 100, 2) if w52h else None
        d["perf_w"]           = perf_w
        d["perf_1m"]          = m.get("Perf.1M")
        d["perf_3m"]          = m.get("Perf.3M")
        d["perf_y"]           = m.get("Perf.Y")
        d["volume"]           = m.get("volume")
        d["weight_pct"]       = None  # filled in second pass
        enriched.append(d)

    # Second pass: portfolio weight
    total_value = sum(s["current_value"] for s in enriched if not s.get("error"))
    for s in enriched:
        if not s.get("error") and total_value:
            s["weight_pct"] = round(s["current_value"] / total_value * 100, 1)
    return enriched


def portfolio_summary(stocks: list) -> dict:
    """Compute portfolio-level totals."""
    valid = [s for s in stocks if not s.get("error")]
    total_cost    = sum(s["cost_basis"]    for s in valid)
    total_value   = sum(s["current_value"] for s in valid)
    total_pnl     = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    # Weekly portfolio gain in LKR
    weekly_lkr_values = [s["weekly_pnl_lkr"] for s in valid if s.get("weekly_pnl_lkr") is not None]
    total_weekly_pnl  = round(sum(weekly_lkr_values), 2) if weekly_lkr_values else None
    total_weekly_pct  = round(total_weekly_pnl / (total_value - total_weekly_pnl) * 100, 2) \
                        if total_weekly_pnl and (total_value - total_weekly_pnl) != 0 else None

    # Best/worst by this week's performance (most relevant for weekly review)
    weekly_valid = [s for s in valid if s.get("perf_w") is not None]
    best_week  = max(weekly_valid, key=lambda s: s["perf_w"], default=None)
    worst_week = min(weekly_valid, key=lambda s: s["perf_w"], default=None)

    # Best/worst overall (since purchase)
    best_overall  = max(valid, key=lambda s: s["pnl_pct"], default=None)
    worst_overall = min(valid, key=lambda s: s["pnl_pct"], default=None)

    return {
        "total_cost":       round(total_cost, 2),
        "total_value":      round(total_value, 2),
        "total_pnl":        round(total_pnl, 2),
        "total_pnl_pct":    round(total_pnl_pct, 2),
        "total_weekly_pnl": total_weekly_pnl,
        "total_weekly_pct": total_weekly_pct,
        "best_week":        best_week,
        "worst_week":       worst_week,
        "best_overall":     best_overall,
        "worst_overall":    worst_overall,
        "stock_count":      len(valid),
        "errors":           len(stocks) - len(valid),
    }


# ─── HTML Generator ────────────────────────────────────────────────────────────

def fmt_lkr(value, decimals=2):
    if value is None:
        return "N/A"
    return f"LKR {value:,.{decimals}f}"

def fmt_pct(value, decimals=2):
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"

def pnl_class(value):
    if value is None:
        return "neutral"
    return "positive" if value >= 0 else "negative"

def pnl_arrow(value):
    if value is None:
        return ""
    return "▲" if value >= 0 else "▼"

def generate_html(stocks: list, summary: dict) -> str:
    generated_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = date.today().isoformat()

    total_pnl_cls  = pnl_class(summary["total_pnl"])
    total_pnl_sign = "+" if summary["total_pnl"] >= 0 else ""
    weekly_cls     = pnl_class(summary.get("total_weekly_pnl"))
    weekly_sign    = "+" if (summary.get("total_weekly_pnl") or 0) >= 0 else ""

    # ── Summary Cards ──
    weekly_lkr_str = f"{weekly_sign}{fmt_lkr(summary['total_weekly_pnl'])}" \
                     if summary.get("total_weekly_pnl") is not None else "N/A"
    weekly_pct_str = f"({weekly_sign}{summary['total_weekly_pct']:.2f}%)" \
                     if summary.get("total_weekly_pct") is not None else ""

    cards_html = f"""
        <div class="card">
            <div class="card-label">Total Invested</div>
            <div class="card-value">{fmt_lkr(summary['total_cost'])}</div>
        </div>
        <div class="card">
            <div class="card-label">Current Value</div>
            <div class="card-value">{fmt_lkr(summary['total_value'])}</div>
        </div>
        <div class="card">
            <div class="card-label">Overall P&amp;L</div>
            <div class="card-value {total_pnl_cls}">
                {pnl_arrow(summary['total_pnl'])} {total_pnl_sign}{fmt_lkr(summary['total_pnl'])}
                <span class="card-sub">{total_pnl_sign}{summary['total_pnl_pct']:.2f}%</span>
            </div>
        </div>
        <div class="card">
            <div class="card-label">This Week</div>
            <div class="card-value {weekly_cls}">
                {pnl_arrow(summary.get('total_weekly_pnl'))} {weekly_lkr_str}
                <span class="card-sub">{weekly_pct_str}</span>
            </div>
        </div>"""

    if summary.get("best_week"):
        bw = summary["best_week"]
        ww = summary["worst_week"]
        cards_html += f"""
        <div class="card">
            <div class="card-label">🏆 Best This Week</div>
            <div class="card-value positive">{bw['symbol'].replace('.N0000','')}
                <span class="card-sub">{fmt_pct(bw['perf_w'])}</span>
            </div>
        </div>
        <div class="card">
            <div class="card-label">📉 Worst This Week</div>
            <div class="card-value negative">{ww['symbol'].replace('.N0000','')}
                <span class="card-sub">{fmt_pct(ww['perf_w'])}</span>
            </div>
        </div>"""

    # ── Stock Table Rows ──
    rows_html = ""
    for s in stocks:
        if s.get("error"):
            rows_html += f"""
            <tr class="error-row">
                <td class="symbol">{s['symbol']}</td>
                <td colspan="13" class="error-msg">⚠ Could not fetch data: {s['error']}</td>
            </tr>"""
            continue

        cp       = s["current_price"]
        bp       = s["buy_price"]
        pnl      = s["pnl_pct"]
        cls      = pnl_class(pnl)
        arr      = pnl_arrow(pnl)
        sym_short = s["symbol"].replace(".N0000", "")
        weight   = s.get("weight_pct")

        # 52W range bar
        w52h = s.get("week52_high")
        w52l = s.get("week52_low")
        bar_html = ""
        if w52h and w52l and w52h != w52l:
            pos = max(0, min(100, (cp - w52l) / (w52h - w52l) * 100))
            bar_html = f"""<div class="range-bar">
                <span class="range-val">{w52l:.1f}</span>
                <div class="bar-track"><div class="bar-fill" style="width:{pos:.0f}%"></div></div>
                <span class="range-val">{w52h:.1f}</span>
            </div>"""

        # % from 52W high badge
        p52 = s.get("pct_from_52w_high")
        p52_html = f'<span class="badge {pnl_class(p52)}">{fmt_pct(p52)}</span>' if p52 is not None else "N/A"

        # Weekly LKR gain
        wk_lkr = s.get("weekly_pnl_lkr")
        wk_cls  = pnl_class(wk_lkr)
        wk_sign = "+" if (wk_lkr or 0) >= 0 else ""
        wk_html = f"{pnl_arrow(wk_lkr)} LKR {abs(wk_lkr):,.2f}" if wk_lkr is not None else "N/A"

        rows_html += f"""
            <tr>
                <td class="symbol">{sym_short}</td>
                <td class="num weight">{weight:.1f}%</td>
                <td class="num">{s['units']:,}</td>
                <td class="num">{bp:.2f}</td>
                <td class="num bold">{cp:.2f}</td>
                <td class="num">{fmt_lkr(s['cost_basis'])}</td>
                <td class="num">{fmt_lkr(s['current_value'])}</td>
                <td class="num {cls}">{arr} {fmt_lkr(s['pnl_lkr'])}</td>
                <td class="num {cls}">{arr} {fmt_pct(pnl)}</td>
                <td class="num {wk_cls}">{wk_html}</td>
                <td class="num {pnl_class(s.get('perf_w'))}">{fmt_pct(s.get('perf_w'))}</td>
                <td class="num {pnl_class(s.get('perf_1m'))}">{fmt_pct(s.get('perf_1m'))}</td>
                <td class="num {pnl_class(s.get('perf_3m'))}">{fmt_pct(s.get('perf_3m'))}</td>
                <td class="num {pnl_class(s.get('perf_y'))}">{fmt_pct(s.get('perf_y'))}</td>
                <td>{p52_html}</td>
                <td>{bar_html}</td>
            </tr>"""

    # ── Chart data ──
    valid_stocks   = [s for s in stocks if not s.get("error")]
    labels         = json.dumps([s["symbol"].replace(".N0000", "") for s in valid_stocks])
    weekly_perf    = json.dumps([s.get("perf_w") or 0 for s in valid_stocks])
    overall_pnl    = json.dumps([s["pnl_pct"] for s in valid_stocks])
    alloc_values   = json.dumps([s["current_value"] for s in valid_stocks])
    weekly_colors  = json.dumps([
        "rgba(34,197,94,0.85)"  if (s.get("perf_w") or 0) >= 0 else "rgba(239,68,68,0.85)"
        for s in valid_stocks
    ])
    overall_colors = json.dumps([
        "rgba(34,197,94,0.85)"  if s["pnl_pct"] >= 0 else "rgba(239,68,68,0.85)"
        for s in valid_stocks
    ])
    donut_colors   = json.dumps([
        "#3b82f6","#8b5cf6","#f59e0b","#10b981","#f43f5e",
        "#06b6d4","#84cc16","#ec4899","#6366f1","#14b8a6",
    ][:len(valid_stocks)])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>CSE Portfolio Report — {today}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f0f4f8; color: #1e293b; padding: 24px 32px; max-width: 1400px; margin: 0 auto; }}
    h1   {{ font-size: 1.7rem; font-weight: 700; color: #0f172a; }}
    .subtitle {{ color: #64748b; font-size: 0.88rem; margin-top: 4px; margin-bottom: 28px; }}

    /* Cards */
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
              gap: 14px; margin-bottom: 28px; }}
    .card {{ background: #fff; border-radius: 12px; padding: 18px 20px;
             box-shadow: 0 1px 4px rgba(0,0,0,.07); }}
    .card-label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: .06em;
                   color: #64748b; margin-bottom: 8px; }}
    .card-value {{ font-size: 1.2rem; font-weight: 700; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }}
    .card-sub   {{ font-size: 0.8rem; font-weight: 500; color: inherit; opacity: .8; }}

    /* Colors */
    .positive {{ color: #16a34a; }}
    .negative {{ color: #dc2626; }}
    .neutral  {{ color: #64748b; }}

    /* Chart row */
    .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }}
    @media (max-width: 768px) {{ .charts-row {{ grid-template-columns: 1fr; }} }}
    .chart-card {{ background: #fff; border-radius: 12px; padding: 20px 24px;
                   box-shadow: 0 1px 4px rgba(0,0,0,.07); }}
    .chart-card h2 {{ font-size: 0.9rem; font-weight: 600; color: #475569; margin-bottom: 16px; }}
    .chart-canvas {{ max-height: 240px; }}
    .donut-canvas {{ max-height: 240px; }}

    /* Table */
    .table-wrap {{ background: #fff; border-radius: 12px; padding: 20px 24px;
                   box-shadow: 0 1px 4px rgba(0,0,0,.07); overflow-x: auto; }}
    .table-wrap h2 {{ font-size: 0.9rem; font-weight: 600; color: #475569; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
    thead tr {{ border-bottom: 2px solid #e2e8f0; }}
    thead th {{ background: #f8fafc; text-align: left; padding: 9px 11px;
                font-size: 0.7rem; text-transform: uppercase; letter-spacing: .05em;
                color: #94a3b8; white-space: nowrap; }}
    tbody tr {{ border-bottom: 1px solid #f1f5f9; transition: background .12s; }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody tr:hover {{ background: #f8fafc; }}
    td {{ padding: 10px 11px; white-space: nowrap; vertical-align: middle; }}
    td.symbol {{ font-weight: 700; color: #0f172a; font-size: 0.92rem; }}
    td.num    {{ text-align: right; font-variant-numeric: tabular-nums; }}
    td.weight {{ text-align: right; font-weight: 600; color: #475569; }}
    td.bold   {{ font-weight: 700; }}
    td.error-msg {{ color: #dc2626; font-size: 0.82rem; }}

    /* Badge (% from 52W high) */
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
    .badge.positive {{ background: #dcfce7; color: #15803d; }}
    .badge.negative {{ background: #fee2e2; color: #b91c1c; }}
    .badge.neutral  {{ background: #f1f5f9; color: #64748b; }}

    /* 52W range bar */
    .range-bar {{ display: flex; align-items: center; gap: 5px; min-width: 150px; }}
    .range-val {{ font-size: 0.7rem; color: #94a3b8; width: 34px; }}
    .range-val:last-child {{ text-align: right; }}
    .bar-track {{ flex: 1; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }}
    .bar-fill  {{ height: 100%; background: #3b82f6; border-radius: 3px; }}

    /* Section divider */
    .section-title {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
                      letter-spacing: .08em; color: #94a3b8; margin: 0 0 14px; }}

    /* Footer */
    .footer {{ margin-top: 28px; font-size: 0.76rem; color: #94a3b8; text-align: center; }}
    a {{ color: #3b82f6; text-decoration: none; }}
  </style>
</head>
<body>
  <h1>📊 CSE Portfolio Report</h1>
  <p class="subtitle">Generated on <span id="generated-local-time" data-generated-utc="{generated_utc_iso}">{report_date}</span> &nbsp;·&nbsp; Data via TradingView &nbsp;·&nbsp; {summary['stock_count']} holdings</p>

  <!-- Summary Cards -->
  <div class="cards">
    {cards_html}
  </div>

  <!-- Charts -->
  <div class="charts-row">
    <div class="chart-card">
      <h2>📅 This Week — Performance (%)</h2>
      <canvas id="weeklyChart" class="chart-canvas"></canvas>
    </div>
    <div class="chart-card">
      <h2>🥧 Portfolio Allocation (by current value)</h2>
      <canvas id="allocChart" class="donut-canvas"></canvas>
    </div>
  </div>

  <!-- Holdings Table -->
  <div class="table-wrap">
    <h2>📋 Individual Holdings</h2>
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th style="text-align:right">Weight</th>
          <th style="text-align:right">Units</th>
          <th style="text-align:right">Buy Price</th>
          <th style="text-align:right">Current</th>
          <th style="text-align:right">Cost Basis</th>
          <th style="text-align:right">Market Value</th>
          <th style="text-align:right">P&amp;L (LKR)</th>
          <th style="text-align:right">P&amp;L %</th>
          <th style="text-align:right">Wk Gain (LKR)</th>
          <th style="text-align:right">1W %</th>
          <th style="text-align:right">1M %</th>
          <th style="text-align:right">3M %</th>
          <th style="text-align:right">1Y %</th>
          <th style="text-align:right">vs 52W High</th>
          <th>52W Range</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <!-- Terminology Guide -->
  <div class="table-wrap" style="margin-top:16px;">
    <h2>📘 Quick Guide (Key Terms)</h2>
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>What it means</th>
          <th>What to look for</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Total Invested</td>
          <td>Total money put into current holdings.</td>
          <td>Reference baseline for P&amp;L.</td>
        </tr>
        <tr>
          <td>Current Value</td>
          <td>What your holdings are worth now at market prices.</td>
          <td>Ideally above Total Invested over time.</td>
        </tr>
        <tr>
          <td>Overall P&amp;L</td>
          <td>Gain/loss since purchase in LKR and %.</td>
          <td>Positive and improving trend is generally healthy.</td>
        </tr>
        <tr>
          <td>This Week / Wk Gain (LKR)</td>
          <td>Estimated gain/loss for the last week.</td>
          <td>Use for short-term movement only; avoid overreacting to one week.</td>
        </tr>
        <tr>
          <td>Weight</td>
          <td>Each stock's share of total portfolio value.</td>
          <td>Avoid over-concentration in one stock (often &lt;30–35%).</td>
        </tr>
        <tr>
          <td>1W / 1M / 3M / 1Y %</td>
          <td>Price return over those time windows.</td>
          <td>Check consistency across periods, not just one timeframe.</td>
        </tr>
        <tr>
          <td>vs 52W High</td>
          <td>Distance from the 52-week peak price.</td>
          <td>Near 0% means near peak; very negative can mean weakness or value.</td>
        </tr>
        <tr>
          <td>52W Range</td>
          <td>Where current price sits between 52-week low and high.</td>
          <td>Use with fundamentals; position alone is not a buy/sell signal.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="footer">
    Prices from <a href="https://www.tradingview.com" target="_blank">TradingView</a>.
    For personal tracking only — not financial advice.
  </p>

  <script>
    // Render generated time in browser local timezone
    (() => {{
      const el = document.getElementById('generated-local-time');
      if (!el) return;
      const iso = el.getAttribute('data-generated-utc');
      const dt = new Date(iso);
      if (Number.isNaN(dt.getTime())) return;
      el.textContent = dt.toLocaleString(undefined, {{ dateStyle: 'medium', timeStyle: 'short' }});
    }})();

    // Weekly performance bar chart
    new Chart(document.getElementById('weeklyChart').getContext('2d'), {{
      type: 'bar',
      data: {{
        labels: {labels},
        datasets: [{{
          label: '1W %',
          data: {weekly_perf},
          backgroundColor: {weekly_colors},
          borderRadius: 6,
          borderSkipped: false,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed.y >= 0 ? '+' : ''}}${{c.parsed.y.toFixed(2)}}%` }} }}
        }},
        scales: {{
          y: {{
            grid: {{ color: '#f1f5f9' }},
            ticks: {{ callback: v => (v >= 0 ? '+' : '') + v + '%', font: {{ size: 11 }} }}
          }},
          x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 12, weight: '600' }} }} }}
        }}
      }}
    }});

    // Allocation donut chart
    new Chart(document.getElementById('allocChart').getContext('2d'), {{
      type: 'doughnut',
      data: {{
        labels: {labels},
        datasets: [{{
          data: {alloc_values},
          backgroundColor: {donut_colors},
          borderWidth: 2,
          borderColor: '#fff',
          hoverOffset: 6,
        }}]
      }},
      options: {{
        responsive: true,
        cutout: '62%',
        plugins: {{
          legend: {{
            position: 'right',
            labels: {{ font: {{ size: 12 }}, padding: 14, usePointStyle: true }}
          }},
          tooltip: {{
            callbacks: {{
              label: c => {{
                const total = c.dataset.data.reduce((a, b) => a + b, 0);
                const pct   = (c.parsed / total * 100).toFixed(1);
                return ` ${{c.label}}: ${{pct}}%`;
              }}
            }}
          }}
        }}
      }}
    }});
  </script>
</body>
</html>
"""



# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("📊 CSE Portfolio Reporter")
    print("─" * 40)
    print("Fetching market data...")

    stocks  = fetch_all_quotes(PORTFOLIO)
    stocks  = calculate(stocks)
    summary = portfolio_summary(stocks)

    print("\n── Summary ──────────────────────────")
    print(f"  Invested : {fmt_lkr(summary['total_cost'])}")
    print(f"  Value    : {fmt_lkr(summary['total_value'])}")
    pnl_sign = "+" if summary["total_pnl"] >= 0 else ""
    print(f"  P&L      : {pnl_sign}{fmt_lkr(summary['total_pnl'])}  ({pnl_sign}{summary['total_pnl_pct']:.2f}%)")
    if summary.get("total_weekly_pnl") is not None:
        wk_sign = "+" if summary["total_weekly_pnl"] >= 0 else ""
        print(f"  This wk  : {wk_sign}{fmt_lkr(summary['total_weekly_pnl'])}  ({wk_sign}{summary['total_weekly_pct']:.2f}%)")
    if summary.get("best_week"):
        print(f"  Best wk  : {summary['best_week']['symbol']}  ({fmt_pct(summary['best_week']['perf_w'])})")
        print(f"  Worst wk : {summary['worst_week']['symbol']}  ({fmt_pct(summary['worst_week']['perf_w'])})")

    html = generate_html(stocks, summary)

    base_dir      = os.path.dirname(os.path.abspath(__file__))
    generated_dir = os.path.join(base_dir, "generated")
    os.makedirs(generated_dir, exist_ok=True)

    browser_file = os.path.join(generated_dir, "portfolio_report.html")

    with open(browser_file, "w", encoding="utf-8") as f:
        f.write(html)

    print("\n✅ Browser report : generated/portfolio_report.html")
    print(f"   Open browser   : file://{browser_file}")


if __name__ == "__main__":
    main()
