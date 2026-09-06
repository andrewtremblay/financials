"""
Tests for retirement_deterministic.py — categories 1, 3, and 7 of the
Retirement Planning spec.

Run with: uv run pytest test_retirement_deterministic.py -v
"""
import pytest

import retirement_deterministic as det
import retirement_shared as shared


def make_settings(**overrides):
    base = {
        "current_age": 35.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
        "current_portfolio_balance": 200000.0, "annual_savings": 20000.0,
        "annual_return_pct": 7.0, "inflation_pct": 3.0, "bond_yield_pct": 4.0,
        "withdrawal_rate_pct": 4.0, "desired_annual_spending": 60000.0,
        "lean_annual_spending": 40000.0, "fat_annual_spending": 120000.0,
        "barista_annual_spending_gap": 20000.0, "social_security_annual": 20000.0,
        "pension_annual": 0.0, "risk_aversion": 3.0,
    }
    base.update(overrides)
    return base


class TestSharedMath:
    def test_real_rate_is_less_than_nominal_when_inflation_positive(self):
        assert det.real_rate_pct(7.0, 3.0) < 7.0
        assert det.real_rate_pct(7.0, 3.0) > 3.0  # roughly 4%, via Fisher not simple subtraction

    def test_future_value_grows_with_contributions_and_return(self):
        fv_no_contrib = shared.future_value_with_contributions(1000.0, 0.0, 7.0, 10.0)
        fv_with_contrib = shared.future_value_with_contributions(1000.0, 500.0, 7.0, 10.0)
        assert fv_with_contrib > fv_no_contrib > 1000.0

    def test_amortized_withdrawal_fully_depletes_balance(self):
        """amortized_withdrawal solves an ordinary annuity: growth applied
        BEFORE each period's withdrawal (end-of-period payment convention)
        — the simulation loop here must match that to correctly verify the
        formula's own contract."""
        balance, rate, years = 1_000_000.0, 5.0, 20.0
        w = det.amortized_withdrawal(balance, rate, years)
        remaining = balance
        for _ in range(int(years)):
            remaining = remaining * (1 + rate / 100) - w
        assert abs(remaining) < 1.0  # depletes to ~zero, not negative or leftover

    def test_amortized_withdrawal_zero_years_returns_whole_balance(self):
        assert det.amortized_withdrawal(1000.0, 5.0, 0) == 1000.0


class TestStraightLineCompounding:
    def test_meets_spending_with_generous_assumptions(self):
        result = det.straight_line_compounding(make_settings(desired_annual_spending=1000.0))
        assert result["meets_desired_spending"] is True
        assert result["balance_at_retirement"] > 0

    def test_fails_with_stingy_assumptions(self):
        result = det.straight_line_compounding(make_settings(
            current_portfolio_balance=0.0, annual_savings=0.0, desired_annual_spending=1_000_000.0,
        ))
        assert result["meets_desired_spending"] is False


class TestVariableReturnSingleSequence:
    def test_returns_a_single_deterministic_trajectory(self):
        result = det.variable_return_single_sequence(make_settings())
        assert result["balance_at_retirement"] > 0
        assert "lasted_full_retirement" in result

    def test_zero_starting_balance_and_savings_stays_at_zero(self):
        result = det.variable_return_single_sequence(make_settings(current_portfolio_balance=0.0, annual_savings=0.0))
        assert result["balance_at_retirement"] == 0.0


class TestCapitalUtilization:
    def test_withdrawal_depletes_to_target_zero(self):
        result = det.capital_utilization(make_settings())
        assert result["target_ending_balance"] == 0.0
        assert result["annual_withdrawal_today_dollars"] > 0


class TestCapitalPreservation:
    def test_principal_untouched_equals_balance_at_retirement(self):
        result = det.capital_preservation(make_settings())
        assert result["principal_preserved"] == result["balance_at_retirement"]
        assert result["annual_yield_spendable"] > 0


class TestFourPercentRule:
    def test_year_one_withdrawal_is_rate_times_balance(self):
        s = make_settings(withdrawal_rate_pct=4.0)
        result = det.four_percent_rule(s)
        expected = result["balance_at_retirement"] * 0.04
        assert abs(result["year_one_withdrawal"] - expected) < 0.01

    def test_final_year_exceeds_year_one_under_positive_inflation(self):
        result = det.four_percent_rule(make_settings())
        assert result["final_year_withdrawal_nominal"] > result["year_one_withdrawal"]


class TestRuleOf25:
    def test_target_is_25x_spending_at_4_percent(self):
        result = det.rule_of_25(make_settings(withdrawal_rate_pct=4.0, desired_annual_spending=50000.0))
        assert result["multiple"] == 25.0
        assert result["target_portfolio"] == 1_250_000.0

    def test_shortfall_is_zero_when_on_track(self):
        result = det.rule_of_25(make_settings(desired_annual_spending=1.0))
        assert result["on_track"] is True
        assert result["shortfall"] == 0.0


class TestConstantPercentage:
    def test_never_fully_depletes(self):
        result = det.constant_percentage(make_settings())
        assert result["ending_balance"] > 0  # percentage-of-remaining-balance can't hit exactly zero


class TestFireVariants:
    def test_lean_fire_target_is_smaller_than_fat_fire(self):
        s = make_settings()
        lean = det.lean_fire(s)
        fat = det.fat_fire(s)
        assert lean["target_portfolio"] < fat["target_portfolio"]

    def test_coast_fire_number_is_less_than_traditional_target(self):
        result = det.coast_fire(make_settings())
        assert result["coast_fire_number"] < result["traditional_retirement_target"]

    def test_coast_fire_already_there_when_balance_exceeds_number(self):
        result = det.coast_fire(make_settings(current_portfolio_balance=10_000_000.0))
        assert result["already_coast_fire"] is True
        assert result["shortfall"] == 0.0

    def test_barista_fire_target_smaller_than_full_fire_for_same_rate(self):
        s = make_settings(barista_annual_spending_gap=20000.0, desired_annual_spending=60000.0)
        barista = det.barista_fire(s)
        rule25 = det.rule_of_25(s)
        assert barista["target_portfolio"] < rule25["target_portfolio"]
