#!/usr/bin/env python3
"""
calculate_returns.py — Generates comparison.json from passive and active portfolio data.
Can be imported as a module or run standalone.

Usage:
    python scripts/calculate_returns.py
"""

import json
import os
from datetime import UTC, date, datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

PURCHASE_FX_RATE = 4.03
START_DATE = date(2026, 1, 16)
ALL_TRANCHES_DATE = date(2026, 3, 9)
STALE_DAYS = 14


def _load_json(filename: str) -> object:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return [] if filename.endswith(".json") else {}
    with open(path) as f:
        return json.load(f)


def _cagr(current: float, invested: float, days: int) -> float:
    if days <= 0 or invested <= 0 or current <= 0:
        return 0.0
    return ((current / invested) ** (365.0 / days) - 1) * 100


def _active_on(active_entries: list, target_date: str):
    """
    Return the most recent active entry on or before target_date.
    Uses hold-last-known-value; returns None if no entry exists yet.
    """
    result = None
    for entry in sorted(active_entries, key=lambda x: x["date"]):
        if entry["date"] <= target_date:
            result = entry
        else:
            break
    return result


def main():
    passive = _load_json("passive_portfolio.json")
    active = _load_json("active_portfolio.json")

    if not passive:
        print("passive_portfolio.json is empty — run backfill.py first.")
        return

    today = date.today()
    today_str = today.isoformat()
    days_elapsed = (today - START_DATE).days

    latest_p = passive[-1]
    live_usd_myr = latest_p["live_usd_myr"]

    # --- Passive metrics ---
    passive_invested = latest_p["total_invested_myr"]
    passive_current = latest_p["total_value_myr"]
    passive_return_pct = latest_p["return_pct"]
    passive_annualised = _cagr(passive_current, passive_invested, days_elapsed)
    # FX contribution: how much of the MYR gain/loss is purely from currency movement
    fx_gain_myr = (live_usd_myr - PURCHASE_FX_RATE) * latest_p["total_invested_usd"]

    # --- Active metrics ---
    latest_a = _active_on(active, today_str)
    if latest_a:
        active_invested = latest_a["total_invested_myr"]
        active_current = latest_a["reported_value_myr"]
        active_last_date = latest_a["date"]
        active_return_pct = (
            (active_current - active_invested) / active_invested * 100
            if active_invested else 0.0
        )
        active_annualised = _cagr(active_current, active_invested, days_elapsed)
        active_stale = (today - date.fromisoformat(active_last_date)).days > STALE_DAYS
    else:
        active_invested = 0.0
        active_current = 0.0
        active_return_pct = 0.0
        active_annualised = 0.0
        active_last_date = None
        active_stale = True

    delta_pct = passive_return_pct - active_return_pct
    if delta_pct > 0:
        winner = "passive"
    elif delta_pct < 0:
        winner = "active"
    else:
        winner = "tied"

    # --- History (one entry per passive trading day) ---
    history = []
    for snap in passive:
        snap_date = snap["date"]
        a = _active_on(active, snap_date)
        if a is None:
            continue
        a_invested = a["total_invested_myr"]
        a_value = a["reported_value_myr"]
        a_ret = (a_value - a_invested) / a_invested * 100 if a_invested else 0.0
        history.append({
            "date": snap_date,
            "days_since_start": (date.fromisoformat(snap_date) - START_DATE).days,
            "passive_return_pct": round(snap["return_pct"], 4),
            "active_return_pct": round(a_ret, 4),
            "passive_value_myr": snap["total_value_myr"],
            "active_value_myr": round(a_value, 2),
        })

    comparison = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_date": START_DATE.isoformat(),
        "all_tranches_deployed_date": ALL_TRANCHES_DATE.isoformat(),
        "days_elapsed": days_elapsed,
        "purchase_fx_rate": PURCHASE_FX_RATE,
        "live_usd_myr": live_usd_myr,
        "passive": {
            "total_invested_myr": passive_invested,
            "total_invested_usd": latest_p["total_invested_usd"],
            "current_value_myr": passive_current,
            "return_pct": round(passive_return_pct, 4),
            "annualised_return_pct": round(passive_annualised, 4),
            "fx_gain_myr": round(fx_gain_myr, 2),
            "voo_allocation": 0.5,
            "vt_allocation": 0.5,
            "webull_fees_total_usd": latest_p["webull_fee_usd"],
        },
        "active": {
            "total_invested_myr": active_invested,
            "current_value_myr": active_current,
            "return_pct": round(active_return_pct, 4),
            "annualised_return_pct": round(active_annualised, 4),
            "last_reported_date": active_last_date,
            "is_stale": active_stale,
        },
        "delta_pct": round(delta_pct, 4),
        "winner": winner,
        "history": history,
    }

    out_path = os.path.join(DATA_DIR, "comparison.json")
    with open(out_path, "w") as f:
        json.dump(comparison, f, indent=2)

    print(
        f"comparison.json written — {len(history)} history entries, "
        f"passive {passive_return_pct:+.2f}% vs active {active_return_pct:+.2f}%, "
        f"winner: {winner}"
    )


if __name__ == "__main__":
    main()
