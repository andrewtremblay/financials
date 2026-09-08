"""
Tests for retirement_data.py's bundled reference data.

Run with: uv run pytest test_retirement_data.py -v
"""
from retirement_data import (
    BOND_ANNUAL_RETURNS,
    IRS_UNIFORM_LIFETIME_TABLE,
    SIMULATION_YEARS,
    SP500_ANNUAL_RETURNS,
    rmd_divisor,
)


def test_simulation_years_matches_sp500_keys_sorted():
    assert SIMULATION_YEARS == sorted(SP500_ANNUAL_RETURNS)


def test_bond_returns_defined_for_every_equity_year():
    assert set(BOND_ANNUAL_RETURNS) == set(SP500_ANNUAL_RETURNS)


def test_at_least_40_years_of_data():
    assert len(SIMULATION_YEARS) >= 40


def test_irs_table_divisors_strictly_decrease_with_age():
    ages = sorted(IRS_UNIFORM_LIFETIME_TABLE)
    divisors = [IRS_UNIFORM_LIFETIME_TABLE[a] for a in ages]
    assert divisors == sorted(divisors, reverse=True)


def test_rmd_divisor_matches_table_for_in_range_age():
    assert rmd_divisor(80) == IRS_UNIFORM_LIFETIME_TABLE[80]
