#!/usr/bin/env python3
"""
fetch_prices.py — Daily incremental update. Runs via GitHub Actions cron at 08:00 MYT.
Fetches the latest trading day's closing prices, updates passive_portfolio.json,
fx_rates.json, and regenerates comparison.json.

Usage:
    python scripts/fetch_prices.py
"""

import json
import os
import sys
from datetime import date, timedelta

import pandas as pd
import requests
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PURCHASE_FX_RATE = 4.03
WEBULL_REG_FEE_RATE = 0.00023
START_DATE = date(2026, 1, 16)

TRANCHES = [
    (date(2026, 1, 16), 30_000.00),
    (date(2026, 1, 22), 25_000.00),
    (date(2026, 1, 27), 32_000.00),
    (date(2026, 3,  9), 13_900.00),
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def fetch_live_usdmyr() -> float:
    """Fetch live USD/MYR rate. Falls back to yfinance if exchangerate.host fails."""
    api_key = os.environ.get("EXCHANGERATE_API_KEY", "")
    if api_key:
        try:
            resp = requests.get(
                "https://api.exchangerate.host/live",
                params={"access_key": api_key, "currencies": "MYR", "source": "USD"},
                timeout=10,
            )
            data = resp.json()
            if data.get("success") and "USDMYR" in data.get("quotes", {}):
                return float(data["quotes"]["USDMYR"])
            print(f"exchangerate.host returned unexpected response: {data}")
        except Exception as e:
            print(f"exchangerate.host failed: {e}")

    print("Falling back to yfinance for USD/MYR rate")
    raw = yf.download("USDMYR=X", period="5d", auto_adjust=False, progress=False)
    s = raw["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return float(s.dropna().iloc[-1])


def fetch_new_rows(since_date: date) -> list:
    """
    Fetch VOO and VT closing prices for trading days strictly after since_date.
    Returns list of (day, voo_price, vt_price) tuples.
    """
    start = (since_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    voo_raw = yf.download("VOO", start=start, end=end, auto_adjust=False, progress=False)
    vt_raw = yf.download("VT", start=start, end=end, auto_adjust=False, progress=False)

    if voo_raw.empty or vt_raw.empty:
        return []

    def to_series(df):
        s = df["Close"]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        s.index = pd.to_datetime(s.index).date
        return s.dropna()

    voo_s = to_series(voo_raw)
    vt_s = to_series(vt_raw)
    common = sorted(set(voo_s.index) & set(vt_s.index))
    return [(d, float(voo_s[d]), float(vt_s[d])) for d in common]


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    passive_path = os.path.join(DATA_DIR, "passive_portfolio.json")
    fx_path = os.path.join(DATA_DIR, "fx_rates.json")

    # Run backfill if no data exists yet
    if not os.path.exists(passive_path):
        print("passive_portfolio.json missing — running backfill first")
        import backfill
        backfill.main()
        return

    with open(passive_path) as f:
        snapshots = json.load(f)

    if not snapshots:
        print("passive_portfolio.json is empty — running backfill first")
        import backfill
        backfill.main()
        return

    with open(fx_path) as f:
        fx_records = json.load(f)

    last_date = date.fromisoformat(snapshots[-1]["date"])
    print(f"Last snapshot: {last_date}")

    new_rows = fetch_new_rows(last_date)
    if not new_rows:
        print("No new trading days — already up to date.")
        return

    usdmyr = fetch_live_usdmyr()
    print(f"Live USD/MYR: {usdmyr:.4f}")

    fx_records.append({
        "date": date.today().isoformat(),
        "usd_myr": round(usdmyr, 4),
    })

    # Rebuild mutable state from the last snapshot
    last = snapshots[-1]
    voo_units = last["voo_units"]
    vt_units = last["vt_units"]
    voo_cost_usd = last["voo_cost_usd"]
    vt_cost_usd = last["vt_cost_usd"]
    webull_fee_total = last["webull_fee_usd"]
    total_invested_myr = last["total_invested_myr"]
    total_invested_usd = last["total_invested_usd"]
    tranches_deployed = last["tranches_deployed"]

    tranche_map = {d: m for d, m in TRANCHES}

    # Fetch VT dividend history for the new date range
    vt_ticker = yf.Ticker("VT")
    all_divs = vt_ticker.dividends
    all_divs.index = pd.to_datetime(all_divs.index).date

    for day, voo_price, vt_price in new_rows:
        day_dividends = []

        # Deploy tranche if scheduled for this day and not yet deployed
        if day in tranche_map and tranches_deployed < len(TRANCHES):
            myr = tranche_map[day]
            tranche_usd = myr / PURCHASE_FX_RATE
            voo_alloc = tranche_usd * 0.5
            vt_alloc = tranche_usd * 0.5
            voo_fee = voo_alloc * WEBULL_REG_FEE_RATE
            vt_fee = vt_alloc * WEBULL_REG_FEE_RATE
            voo_units += (voo_alloc - voo_fee) / voo_price
            vt_units += (vt_alloc - vt_fee) / vt_price
            voo_cost_usd += voo_alloc
            vt_cost_usd += vt_alloc
            webull_fee_total += voo_fee + vt_fee
            total_invested_myr += myr
            total_invested_usd += tranche_usd
            tranches_deployed += 1

        # Reinvest VT dividend if ex-dividend date
        if day in all_divs.index and vt_units > 0:
            div_per_unit = float(all_divs[day])
            div_total = div_per_unit * vt_units
            units_added = div_total / vt_price
            vt_units += units_added
            day_dividends.append({
                "date": day.isoformat(),
                "vt_dividend_usd": round(div_total, 6),
                "units_added": round(units_added, 6),
            })

        voo_value_myr = voo_units * voo_price * usdmyr
        vt_value_myr = vt_units * vt_price * usdmyr
        total_value_myr = voo_value_myr + vt_value_myr
        return_myr = total_value_myr - total_invested_myr
        return_pct = return_myr / total_invested_myr * 100 if total_invested_myr else 0.0

        snapshots.append({
            "date": day.isoformat(),
            "voo_price_usd": round(voo_price, 4),
            "vt_price_usd": round(vt_price, 4),
            "live_usd_myr": round(usdmyr, 4),
            "voo_units": round(voo_units, 6),
            "vt_units": round(vt_units, 6),
            "voo_cost_usd": round(voo_cost_usd, 4),
            "vt_cost_usd": round(vt_cost_usd, 4),
            "webull_fee_usd": round(webull_fee_total, 6),
            "total_invested_myr": round(total_invested_myr, 2),
            "total_invested_usd": round(total_invested_usd, 4),
            "voo_value_myr": round(voo_value_myr, 2),
            "vt_value_myr": round(vt_value_myr, 2),
            "total_value_myr": round(total_value_myr, 2),
            "return_myr": round(return_myr, 2),
            "return_pct": round(return_pct, 4),
            "tranches_deployed": tranches_deployed,
            "dividends": day_dividends,
        })
        print(f"  {day}: VOO=${voo_price:.2f}, VT=${vt_price:.2f}, Value=RM{total_value_myr:,.2f}, Return={return_pct:+.2f}%")

    with open(passive_path, "w") as f:
        json.dump(snapshots, f, indent=2)
    with open(fx_path, "w") as f:
        json.dump(fx_records, f, indent=2)

    print(f"\nAdded {len(new_rows)} new snapshot(s) to passive_portfolio.json")

    import calculate_returns
    calculate_returns.main()


if __name__ == "__main__":
    main()
