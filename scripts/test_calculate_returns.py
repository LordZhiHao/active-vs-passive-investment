"""
Unit tests for calculate_returns.py

Run with:
    pytest scripts/test_calculate_returns.py -v

Tests cover:
  - Pure calculation functions (_cagr, _active_on)
  - Known first-tranche values from the live backfill data
  - Edge cases (zero division, stale detection, no active data)
"""

import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calculate_returns as cr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

PURCHASE_FX_RATE = 4.03
WEBULL_REG_FEE_RATE = 0.00023

# Deposit schedule constants (MYR → USD at fixed 4.03)
TRANCHE_1_MYR = 30_000.00
TRANCHE_1_USD = TRANCHE_1_MYR / PURCHASE_FX_RATE  # 7444.1688...


# ---------------------------------------------------------------------------
# _cagr
# ---------------------------------------------------------------------------

class TestCagr:
    def test_known_doubling_in_one_year(self):
        result = cr._cagr(current=200.0, invested=100.0, days=365)
        assert abs(result - 100.0) < 0.01

    def test_no_gain(self):
        result = cr._cagr(current=100.0, invested=100.0, days=365)
        assert abs(result) < 0.001

    def test_zero_days_returns_zero(self):
        assert cr._cagr(100.0, 100.0, days=0) == 0.0

    def test_zero_invested_returns_zero(self):
        assert cr._cagr(100.0, invested=0.0, days=100) == 0.0

    def test_zero_current_returns_zero(self):
        assert cr._cagr(current=0.0, invested=100.0, days=100) == 0.0

    def test_negative_days_returns_zero(self):
        assert cr._cagr(100.0, 100.0, days=-1) == 0.0

    def test_annualises_correctly_for_half_year(self):
        # 10% gain over ~182 days → CAGR ≈ 21%
        result = cr._cagr(current=110.0, invested=100.0, days=182)
        assert 20.0 < result < 22.0

    def test_loss_gives_negative_cagr(self):
        result = cr._cagr(current=90.0, invested=100.0, days=365)
        assert abs(result - (-10.0)) < 0.01


# ---------------------------------------------------------------------------
# _active_on — hold-last-known-value lookup
# ---------------------------------------------------------------------------

SAMPLE_ACTIVE = [
    {"date": "2026-01-16", "reported_value_myr": 30000.0, "total_invested_myr": 30000.0},
    {"date": "2026-01-22", "reported_value_myr": 55000.0, "total_invested_myr": 55000.0},
    {"date": "2026-03-09", "reported_value_myr": 100900.0, "total_invested_myr": 100900.0},
]


class TestActiveOn:
    def test_exact_match_returns_entry(self):
        entry = cr._active_on(SAMPLE_ACTIVE, "2026-01-22")
        assert entry["reported_value_myr"] == 55000.0

    def test_date_between_entries_holds_last(self):
        # Jan 20 is between Jan 16 and Jan 22 — should return Jan 16 entry
        entry = cr._active_on(SAMPLE_ACTIVE, "2026-01-20")
        assert entry["date"] == "2026-01-16"
        assert entry["reported_value_myr"] == 30000.0

    def test_date_after_last_entry_returns_last(self):
        entry = cr._active_on(SAMPLE_ACTIVE, "2026-04-23")
        assert entry["date"] == "2026-03-09"

    def test_date_before_first_entry_returns_none(self):
        assert cr._active_on(SAMPLE_ACTIVE, "2026-01-01") is None

    def test_empty_entries_returns_none(self):
        assert cr._active_on([], "2026-04-01") is None

    def test_single_entry_after_target_returns_none(self):
        entries = [{"date": "2026-06-01", "reported_value_myr": 100.0, "total_invested_myr": 100.0}]
        assert cr._active_on(entries, "2026-01-16") is None

    def test_unsorted_entries_still_works(self):
        shuffled = [SAMPLE_ACTIVE[2], SAMPLE_ACTIVE[0], SAMPLE_ACTIVE[1]]
        entry = cr._active_on(shuffled, "2026-01-23")
        assert entry["date"] == "2026-01-22"


# ---------------------------------------------------------------------------
# Deposit + fee arithmetic
# ---------------------------------------------------------------------------

class TestDepositArithmetic:
    def test_tranche1_usd_conversion(self):
        expected = 30_000.00 / 4.03
        assert abs(TRANCHE_1_USD - expected) < 0.01

    def test_tranche1_fee_usd(self):
        fee = TRANCHE_1_USD * WEBULL_REG_FEE_RATE
        assert abs(fee - 1.712) < 0.01  # CLAUDE.md example: ~1.71

    def test_all_tranches_total_usd(self):
        tranches_myr = [30_000, 25_000, 32_000, 13_900]
        total_usd = sum(m / PURCHASE_FX_RATE for m in tranches_myr)
        assert abs(total_usd - 25_037.22) < 0.10  # CLAUDE.md: USD 25,037.22

    def test_all_tranches_total_fees(self):
        tranches_myr = [30_000, 25_000, 32_000, 13_900]
        total_fee = sum((m / PURCHASE_FX_RATE) * WEBULL_REG_FEE_RATE for m in tranches_myr)
        assert abs(total_fee - 5.76) < 0.05  # CLAUDE.md: ~USD 5.76

    def test_return_pct_formula(self):
        invested = 100_000.0
        current = 107_500.0
        pct = (current - invested) / invested * 100
        assert abs(pct - 7.5) < 0.001

    def test_fx_gain_formula(self):
        # If USD/MYR moved from 4.03 to 4.48 and total invested is USD 25,037
        fx_gain = (4.48 - 4.03) * 25_037.22
        assert abs(fx_gain - 11_266.75) < 1.0

    def test_fx_drag_when_myr_strengthens(self):
        # If USD/MYR dropped from 4.03 to 3.96, portfolio loses MYR value
        fx_gain = (3.96 - 4.03) * 25_037.22
        assert fx_gain < 0


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_fresh_entry_not_stale(self):
        last = date.today()
        stale = (date.today() - last).days > cr.STALE_DAYS
        assert stale is False

    def test_entry_over_14_days_is_stale(self):
        from datetime import timedelta
        last = date.today() - timedelta(days=15)
        stale = (date.today() - last).days > cr.STALE_DAYS
        assert stale is True

    def test_exactly_14_days_not_stale(self):
        from datetime import timedelta
        last = date.today() - timedelta(days=14)
        stale = (date.today() - last).days > cr.STALE_DAYS
        assert stale is False


# ---------------------------------------------------------------------------
# Integration — validate against live backfill data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def passive_data():
    path = os.path.join(DATA_DIR, "passive_portfolio.json")
    if not os.path.exists(path):
        pytest.skip("passive_portfolio.json not found — run backfill.py first")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def comparison_data():
    path = os.path.join(DATA_DIR, "comparison.json")
    if not os.path.exists(path):
        pytest.skip("comparison.json not found — run calculate_returns.py first")
    with open(path) as f:
        return json.load(f)


class TestLiveData:
    def test_first_snapshot_is_jan16(self, passive_data):
        assert passive_data[0]["date"] == "2026-01-16"

    def test_first_snapshot_invested_myr(self, passive_data):
        assert passive_data[0]["total_invested_myr"] == 30_000.00

    def test_first_snapshot_invested_usd(self, passive_data):
        assert abs(passive_data[0]["total_invested_usd"] - 7444.17) < 0.10

    def test_first_snapshot_fee(self, passive_data):
        assert abs(passive_data[0]["webull_fee_usd"] - 1.712) < 0.01

    def test_first_snapshot_tranches_deployed(self, passive_data):
        assert passive_data[0]["tranches_deployed"] == 1

    def test_all_four_tranches_eventually_deployed(self, passive_data):
        assert passive_data[-1]["tranches_deployed"] == 4

    def test_units_only_increase_or_stay_same(self, passive_data):
        prev_voo = 0.0
        prev_vt = 0.0
        for snap in passive_data:
            assert snap["voo_units"] >= prev_voo - 1e-9
            assert snap["vt_units"] >= prev_vt - 1e-9
            prev_voo = snap["voo_units"]
            prev_vt = snap["vt_units"]

    def test_fourth_tranche_deployed_on_or_after_mar9(self, passive_data):
        deployment_date = next(
            s["date"] for s in passive_data if s["tranches_deployed"] == 4
        )
        assert deployment_date >= "2026-03-09"

    def test_total_invested_matches_deposit_schedule(self, passive_data):
        final = passive_data[-1]
        assert final["total_invested_myr"] == 100_900.00
        assert abs(final["total_invested_usd"] - 25_037.22) < 0.10

    def test_total_fees_near_expected(self, passive_data):
        assert abs(passive_data[-1]["webull_fee_usd"] - 5.76) < 0.05

    def test_comparison_has_required_fields(self, comparison_data):
        for field in ("passive", "active", "delta_pct", "winner", "history", "live_usd_myr"):
            assert field in comparison_data

    def test_comparison_history_has_days_since_start(self, comparison_data):
        first = comparison_data["history"][0]
        assert "days_since_start" in first
        assert first["days_since_start"] == 0  # Jan 16 is day 0

    def test_comparison_history_days_increase(self, comparison_data):
        days = [h["days_since_start"] for h in comparison_data["history"]]
        assert days == sorted(days)
        assert days[0] == 0

    def test_winner_is_valid(self, comparison_data):
        assert comparison_data["winner"] in ("passive", "active", "tied")

    def test_active_is_stale_with_placeholder_data(self, comparison_data):
        # Placeholder data has last_reported_date = 2026-03-09, which is > 14 days ago
        assert comparison_data["active"]["is_stale"] is True
