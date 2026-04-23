# CLAUDE.md — Passive vs Active Portfolio Tracker

## Project overview

A public web app that compares a **simulated passive ETF portfolio** (50% VOO + 50% VT) against a **real active investor's portfolio** (@doitduit.xg on TikTok) that has been documented publicly since January 2026. The passive portfolio is hypothetical but uses real historical price data. The active portfolio values are manually updated from the investor's own public posts.

The goal is twofold:
1. Content for a Malaysian personal finance/data creator — shareable, embeddable, mobile-friendly
2. A long-running experiment that updates periodically and tells a compelling data story over time

The app must be **publicly accessible via a clean URL**, work on mobile, and be deployable for free.

---

## ETF choices and rationale

### VOO — Vanguard S&P 500 ETF
Tracks the S&P 500. US-only, large-cap. Available on Webull. Expense ratio: 0.03%.

### VT — Vanguard Total World Stock ETF *(replaces VWRA)*
VWRA (Vanguard FTSE All-World UCITS ETF) is listed on the **London Stock Exchange** and is **not available on Webull**, which is a US broker. VT is the closest US-listed equivalent:

| | VWRA | VT |
|---|---|---|
| Issuer | Vanguard | Vanguard |
| Index | FTSE All-World | FTSE Global All Cap |
| Coverage | ~3,800 stocks, 49 countries | ~9,500 stocks, 50+ countries |
| Expense ratio | 0.19% | **0.06%** |
| Listed on | London Stock Exchange | NYSE (Webull ✓) |
| Accumulating | Yes | No (pays dividends quarterly) |

VT is actually more diversified (includes small caps) and cheaper. Dividends paid by VT are tracked and treated as reinvested on the ex-dividend date to maintain a fair total return comparison.

---

## Deposit schedule (mirrors the active investor's actual tranches)

The simulation does **not** invest a lump sum on day one. It mirrors the investor's exact deposit dates and amounts at the **fixed conversion rate of RM4.03/USD** (his stated effective blended rate across all conversions).

| Date | MYR deposited | USD equivalent (÷ 4.03) | VOO (50%) | VT (50%) |
|---|---|---|---|---|
| 2026-01-16 | RM 30,000 | USD 7,444.17 | USD 3,722.09 | USD 3,722.09 |
| 2026-01-22 | RM 25,000 | USD 6,203.47 | USD 3,101.74 | USD 3,101.74 |
| 2026-01-27 | RM 32,000 | USD 7,940.45 | USD 3,970.22 | USD 3,970.22 |
| 2026-03-09 | RM 13,900 | USD 3,449.13 | USD 1,724.57 | USD 1,724.57 |
| **Total** | **RM 100,900** | **USD 25,037.22** | | |

On each deposit date, the simulation buys VOO and VT at that day's closing price using the USD amount above. Units are calculated to full precision (fractional units allowed in simulation).

**Simulation start date:** `2026-01-16`

---

## FX rate handling

Two different rates apply at different stages — this distinction is important:

| Stage | Rate used | Reason |
|---|---|---|
| Initial purchase (MYR → USD) | **Fixed RM4.03/USD** for all 4 tranches | Mirrors the investor's actual blended conversion rate |
| Current valuation (USD → MYR) | **Live MYR/USD spot rate** (fetched daily) | Reflects what the portfolio is actually worth in MYR today |

The passive portfolio's MYR value will fluctuate with currency movements even if ETF prices are flat — this is realistic and creates good content (FX drag/tailwind is part of the overseas investing story).

The `fx_rates.json` file only needs to store live rates from app launch onwards. Historical rates are not needed since purchase price is locked at 4.03.

---

## Brokerage: Webull

The active investor uses Webull. The passive simulation uses Webull fee assumptions for a fair comparison.

**Webull fee structure for US ETFs:**
- Commission: **$0.00** (commission-free for US stocks and ETFs)
- Regulatory fees (SEC + FINRA): approximately **$0.23 per $1,000 traded** — applied at purchase only
- No inactivity fees, no withdrawal fees (ACH), no platform fee for US-listed securities

**Applied to the simulation:**
- Each tranche purchase incurs: `tranche_value_usd × 0.00023`
- Fee deducted from available USD before buying units
- Total estimated fees across all 4 tranches ≈ **USD 5.76** — small but tracked for completeness
- No ongoing fees beyond ETF expense ratios (VOO 0.03%, VT 0.06%)

---

## Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Data fetching | Python + `yfinance` | Free, reliable historical + live ETF prices |
| Exchange rates | `exchangerate.host` free tier | Live MYR/USD rate for daily valuation |
| Data store | JSON flat files (upgrade to SQLite if needed) | Simple, no DB setup required early |
| Frontend | React + Recharts | Easy charting, component-based |
| Hosting | Vercel (frontend) + GitHub Actions (data refresh cron) | Free tier sufficient |
| Styling | Tailwind CSS | Utility-first, mobile-friendly out of the box |

---

## Repository structure

```
portfolio-tracker/
├── CLAUDE.md                  # This file
├── README.md
├── data/
│   ├── passive_portfolio.json # Daily snapshots of the passive portfolio
│   ├── active_portfolio.json  # Manually updated active portfolio entries
│   ├── fx_rates.json          # Live MYR/USD rate history (app launch onwards)
│   └── comparison.json        # Generated output consumed by the frontend
├── scripts/
│   ├── fetch_prices.py        # Fetches ETF prices + live FX rate, updates JSONs
│   ├── backfill.py            # One-off: backfills data from 2026-01-16 to today
│   └── calculate_returns.py   # All return and comparison calculations
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PerformanceChart.jsx
│   │   │   ├── StatsCard.jsx
│   │   │   └── LastUpdated.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── public/
│   └── package.json
└── .github/
    └── workflows/
        └── refresh_data.yml   # Cron job: runs fetch_prices.py daily at 08:00 MYT
```

---

## Phase 1 — Data foundation

**Goal:** Reliable data pipeline with backfilled history from 2026-01-16.

### Tasks

- [ ] Set up Python environment (`requirements.txt`: `yfinance`, `requests`, `pandas`)
- [ ] Write `backfill.py` to fetch VOO and VT daily closing prices from `2026-01-16` to today
- [ ] Write `fetch_prices.py` for daily incremental updates (runs via cron)
- [ ] Fetch live MYR/USD rate daily (valuation only — no historical FX fetch needed)
- [ ] Apply deposit schedule: simulate tranche purchases on each deposit date at that day's closing price
- [ ] Deduct Webull regulatory fee (`× 0.00023`) from each tranche before buying units
- [ ] Handle VT dividends: on each ex-dividend date, calculate dividend received and add equivalent VT units at closing price
- [ ] Structure `passive_portfolio.json` as a list of daily snapshots (schema below)
- [ ] Manually seed `active_portfolio.json` with the investor's self-reported values and dates
- [ ] Validate: manually verify unit counts and MYR values for the first tranche (2026-01-16)

### passive_portfolio.json schema

Each entry represents the portfolio's state at end of that day. Units accumulate across tranches.

```json
[
  {
    "date": "2026-01-16",
    "voo_price_usd": 543.21,
    "vt_price_usd": 112.34,
    "live_usd_myr": 4.48,
    "voo_units": 6.85,
    "vt_units": 33.13,
    "voo_cost_usd": 3722.09,
    "vt_cost_usd": 3722.09,
    "webull_fee_usd": 1.71,
    "total_invested_myr": 30000.00,
    "total_invested_usd": 7444.17,
    "voo_value_myr": 15393.12,
    "vt_value_myr": 14824.11,
    "total_value_myr": 30217.23,
    "return_myr": 217.23,
    "return_pct": 0.72,
    "tranches_deployed": 1,
    "dividends": []
  }
]
```

Key field notes:
- `live_usd_myr`: spot rate used for valuation only, not for purchase
- `voo_units` / `vt_units`: cumulative totals, grow as each tranche is deployed
- `total_invested_myr`: cumulative MYR deposited so far (grows at each tranche)
- `tranches_deployed`: 1 through 4, useful for debugging and UI tranche markers
- `dividends`: array of `{ "date": "...", "vt_dividend_usd": 0.32, "units_added": 0.15 }` entries

### active_portfolio.json schema

```json
[
  {
    "date": "2026-01-16",
    "reported_value_myr": 30000.00,
    "total_invested_myr": 30000.00,
    "note": "First deposit — RM30k converted at effective RM4.03/USD",
    "source_url": "https://www.tiktok.com/@doitduit.xg/..."
  },
  {
    "date": "2026-04-15",
    "reported_value_myr": 104230.00,
    "total_invested_myr": 100900.00,
    "note": "Monthly portfolio update post",
    "source_url": "https://www.tiktok.com/@doitduit.xg/..."
  }
]
```

### Key calculations (in `calculate_returns.py`)

```python
PURCHASE_FX_RATE = 4.03        # Fixed — never fetched, never changed
WEBULL_REG_FEE_RATE = 0.00023  # SEC + FINRA combined

# Return metrics
total_return_pct = (current_value_myr - total_invested_myr) / total_invested_myr * 100
days_elapsed = (today - date(2026, 1, 16)).days
cagr = (current_value_myr / total_invested_myr) ** (365 / days_elapsed) - 1

# FX contribution (how much of the gain/loss is currency movement)
fx_gain_myr = (live_usd_myr - PURCHASE_FX_RATE) * total_invested_usd

# Webull fee per tranche
fee_usd = tranche_value_usd * WEBULL_REG_FEE_RATE
```

---

## Phase 2 — Comparison logic

**Goal:** A clean comparison layer that produces delta metrics consumed by the frontend.

### Tasks

- [ ] Write `calculate_returns.py` with functions for both portfolios
- [ ] Output `comparison.json` (frontend reads this directly — no API needed)
- [ ] Handle missing active portfolio dates by **holding last known value** (no interpolation) — show a staleness warning instead
- [ ] Use `return_pct` as the primary comparison metric, not absolute MYR — keeps the comparison fair during the tranche deployment period (Jan 16 – Mar 9) when total invested amounts differ between portfolios
- [ ] Add `days_since_start` using `2026-01-16` as day zero for both portfolios
- [ ] Unit test return calculations with known values before connecting to live data

### comparison.json schema

```json
{
  "generated_at": "2026-04-23T10:00:00Z",
  "start_date": "2026-01-16",
  "all_tranches_deployed_date": "2026-03-09",
  "days_elapsed": 97,
  "purchase_fx_rate": 4.03,
  "live_usd_myr": 4.48,
  "passive": {
    "total_invested_myr": 100900.00,
    "total_invested_usd": 25037.22,
    "current_value_myr": 108450.00,
    "return_pct": 7.48,
    "annualised_return_pct": 28.4,
    "fx_gain_myr": 1130.00,
    "voo_allocation": 0.5,
    "vt_allocation": 0.5,
    "webull_fees_total_usd": 5.76
  },
  "active": {
    "total_invested_myr": 100900.00,
    "current_value_myr": 104230.00,
    "return_pct": 3.30,
    "annualised_return_pct": 12.4,
    "last_reported_date": "2026-04-15",
    "is_stale": false
  },
  "delta_pct": 4.18,
  "winner": "passive",
  "history": [
    {
      "date": "2026-01-16",
      "passive_return_pct": 0.0,
      "active_return_pct": 0.0,
      "passive_value_myr": 30000,
      "active_value_myr": 30000
    }
  ]
}
```

`is_stale` is `true` when `last_reported_date` is more than 14 days ago.

---

## Phase 3 — Frontend

**Goal:** A clean, mobile-first React app that reads `comparison.json` and renders the comparison visually.

### Tasks

- [ ] Scaffold React app with Vite + Tailwind CSS
- [ ] `PerformanceChart.jsx` — Recharts `LineChart` plotting `passive_return_pct` vs `active_return_pct` over time (percentage-based so tranches don't distort scale)
- [ ] Add vertical dashed reference lines on chart at each tranche date (Jan 16, Jan 22, Jan 27, Mar 9) labelled "Deposit"
- [ ] `StatsCard.jsx` — reusable card with metric, label, and colour-coded delta
- [ ] Stat cards: Total return %, Annualised return %, Current value (MYR), FX contribution (MYR)
- [ ] `LastUpdated.jsx` — shows `generated_at` and `last_reported_date`; shows a yellow stale badge if `is_stale: true`
- [ ] Timeline toggle: "From start (Jan 16)" vs "Last 30 days" vs "Last 90 days"
- [ ] Disclaimer footer (see layout below)
- [ ] Mobile-first: stat cards stack vertically on small screens

### UI layout (mobile-first)

```
[Header: "RM100k Challenge — Passive vs Active"]
[Subheader: Started 16 Jan 2026 · Updated 23 Apr 2026]

[Stats row]
  Passive: +7.48%      Active: +3.30%
  Passive leads by 4.18 percentage points

[Line chart — return % over time, full width]
[Deposit markers at: Jan 16, Jan 22, Jan 27, Mar 9]

[Toggle: From start | 30d | 90d]

[FX note: "RM1,130 of passive gain is from MYR weakening vs USD"]
[Fee note: "Webull fees applied: ~USD 5.76 total (regulatory only, zero commission)"]
[Disclaimer: Passive portfolio is simulated using historical prices.
 Active portfolio values are self-reported by @doitduit.xg. Not financial advice.]
```

---

## Data refresh strategy

- **Daily cron** via GitHub Actions runs `fetch_prices.py` at 08:00 MYT (00:00 UTC)
- Script fetches previous day's closing prices for VOO and VT, fetches live MYR/USD rate, runs `calculate_returns.py`, and commits updated `passive_portfolio.json`, `fx_rates.json`, and `comparison.json` back to repo
- Vercel auto-deploys on every commit — no manual deploy step needed
- Active portfolio updates are manual: edit `active_portfolio.json` and push whenever @doitduit.xg posts an update

---

## Content integration notes

- The app URL goes in every video description and pinned comment
- Keep the chart clean enough for direct screen recording in videos
- The deposit markers on the chart tell a natural story: "he deposited on this date, I would have done the same"
- The FX contribution stat is a content hook: "X% of the passive gain is just currency movement — is that real wealth?"
- When @doitduit.xg posts an update, that's a content trigger: update the JSON, push, post a short-form reaction
- The backfilled data from Phase 1 means the first video can already show ~3 months of comparison from day one

---

## Conventions

- All monetary values stored and calculated in **MYR** unless explicitly suffixed `_usd`
- Dates are **ISO 8601** strings (`YYYY-MM-DD`) throughout
- `PURCHASE_FX_RATE = 4.03` is a constant in `calculate_returns.py` — never fetched, never overridden
- The active investor's TikTok handle (`@doitduit.xg`) appears in the UI disclaimer and `active_portfolio.json` source URLs only — never in logic or calculations
- Return percentages stored as plain floats (e.g. `7.48`, not `0.0748`)
- Primary comparison metric is **return %** not absolute MYR value — keeps comparison fair during tranche deployment period
- Frontend is read-only — no user auth, no browser write operations
- Python scripts runnable standalone: `python scripts/fetch_prices.py`