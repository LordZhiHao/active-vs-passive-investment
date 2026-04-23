#!/usr/bin/env python3
"""
backfill.py — One-off script to populate passive_portfolio.json from 2026-01-16 to today.
Run once to initialise history, then use fetch_prices.py for daily incremental updates.

Usage:
    python scripts/backfill.py
"""

import json
import os
import sys
from datetime import date, timedelta

import pandas as pd
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


def _to_series(df: pd.DataFrame, col: str = "Close") -> pd.Series:
    """Extract a column as a Series with plain date index, dropping NaNs."""
    s = df[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index).date
    return s.dropna()


def fetch_price_series(ticker: str) -> pd.Series:
    today = date.today()
    raw = yf.download(
        ticker,
        start=START_DATE.strftime("%Y-%m-%d"),
        end=(today + timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=False,
        progress=False,
    )
    return _to_series(raw, "Close")


def fetch_vt_dividends() -> dict:
    divs = yf.Ticker("VT").dividends
    divs.index = pd.to_datetime(divs.index).date
    return {d: float(v) for d, v in divs.items() if d >= START_DATE}


def build_snapshots(
    voo_close: pd.Series,
    vt_close: pd.Series,
    fx_close: pd.Series,
    dividends: dict,
) -> list:
    trading_days = sorted(voo_close.index)

    # Forward-fill FX onto trading-day calendar (forex has gaps on non-trading days)
    fx_aligned = fx_close.reindex(trading_days).ffill().bfill()

    # Map each tranche to the next available trading day (in case of holidays)
    trading_set = set(trading_days)
    tranche_map = {}
    for tranche_date, myr in TRANCHES:
        d = tranche_date
        while d not in trading_set:
            d += timedelta(days=1)
        if d != tranche_date:
            print(f"  Tranche {tranche_date} advanced to next trading day: {d}")
        tranche_map[d] = tranche_map.get(d, 0.0) + myr

    voo_units = 0.0
    vt_units = 0.0
    voo_cost_usd = 0.0
    vt_cost_usd = 0.0
    webull_fee_total = 0.0
    total_invested_myr = 0.0
    total_invested_usd = 0.0
    tranches_deployed = 0

    snapshots = []

    for day in trading_days:
        if day < START_DATE:
            continue
        if day not in vt_close.index:
            continue

        voo_price = float(voo_close[day])
        vt_price = float(vt_close[day])
        usdmyr = float(fx_aligned[day]) if day in fx_aligned.index else 4.48

        day_dividends = []

        # Deploy tranche if this is a scheduled deposit date
        if day in tranche_map:
            tranches_deployed += 1
            myr = tranche_map[day]
            tranche_usd = myr / PURCHASE_FX_RATE
            voo_alloc = tranche_usd * 0.5
            vt_alloc = tranche_usd * 0.5
            voo_fee = voo_alloc * WEBULL_REG_FEE_RATE
            vt_fee = vt_alloc * WEBULL_REG_FEE_RATE
            # Buy units after deducting regulatory fee
            voo_units += (voo_alloc - voo_fee) / voo_price
            vt_units += (vt_alloc - vt_fee) / vt_price
            voo_cost_usd += voo_alloc
            vt_cost_usd += vt_alloc
            webull_fee_total += voo_fee + vt_fee
            total_invested_myr += myr
            total_invested_usd += tranche_usd

        # Reinvest VT dividends at closing price on ex-dividend date
        if day in dividends and vt_units > 0:
            div_per_unit = dividends[day]
            div_total = div_per_unit * vt_units
            units_added = div_total / vt_price
            vt_units += units_added
            day_dividends.append({
                "date": day.isoformat(),
                "vt_dividend_usd": round(div_total, 6),
                "units_added": round(units_added, 6),
            })

        # Skip days before the first tranche is deployed
        if total_invested_myr == 0:
            continue

        voo_value_myr = voo_units * voo_price * usdmyr
        vt_value_myr = vt_units * vt_price * usdmyr
        total_value_myr = voo_value_myr + vt_value_myr
        return_myr = total_value_myr - total_invested_myr
        return_pct = return_myr / total_invested_myr * 100

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

    return snapshots


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Fetching VOO prices...")
    voo_close = fetch_price_series("VOO")
    print(f"  {len(voo_close)} trading days")

    print("Fetching VT prices...")
    vt_close = fetch_price_series("VT")
    print(f"  {len(vt_close)} trading days")

    print("Fetching historical USD/MYR rates (for backfill valuation)...")
    fx_close = fetch_price_series("USDMYR=X")
    print(f"  {len(fx_close)} data points")

    print("Fetching VT dividend history...")
    dividends = fetch_vt_dividends()
    print(f"  {len(dividends)} dividend event(s) since {START_DATE}")

    snapshots = build_snapshots(voo_close, vt_close, fx_close, dividends)

    out_path = os.path.join(DATA_DIR, "passive_portfolio.json")
    with open(out_path, "w") as f:
        json.dump(snapshots, f, indent=2)
    print(f"\nWrote {len(snapshots)} snapshots to {out_path}")

    # Print first snapshot for manual validation
    if snapshots:
        first = snapshots[0]
        print(f"\nValidation — first snapshot ({first['date']}):")
        print(f"  VOO price:    ${first['voo_price_usd']}")
        print(f"  VT  price:    ${first['vt_price_usd']}")
        print(f"  VOO units:    {first['voo_units']}")
        print(f"  VT  units:    {first['vt_units']}")
        print(f"  Webull fees:  ${first['webull_fee_usd']}")
        print(f"  USD/MYR:      {first['live_usd_myr']}")
        print(f"  Total value:  RM{first['total_value_myr']:,.2f}")
        print(f"  Return:       {first['return_pct']:.4f}%")
        print(f"  (Expected invested: RM30,000.00, fee ~= USD 1.71)")

    # Initialise fx_rates.json if missing (populated by fetch_prices.py going forward)
    fx_path = os.path.join(DATA_DIR, "fx_rates.json")
    if not os.path.exists(fx_path) or open(fx_path).read().strip() in ("", "[]"):
        with open(fx_path, "w") as f:
            json.dump([], f, indent=2)
        print(f"\nInitialised {fx_path}")

    print("\nGenerating comparison.json...")
    import calculate_returns
    calculate_returns.main()


if __name__ == "__main__":
    main()
