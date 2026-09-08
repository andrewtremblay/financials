"""
Tests for retirement_actuarial.py — category 5 of the Retirement Planning
spec (Life Expectancy Method, IRS RMD Math, Gompertz-Makeham).

Run with: uv run pytest test_retirement_actuarial.py -v
"""
import retirement_actuarial as act
from retirement_data import IRS_UNIFORM_LIFETIME_TABLE, rmd_divisor


def make_settings(**overrides):
    base = {
        "current_age": 65.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
        "current_portfolio_balance": 1_000_000.0, "annual_savings": 0.0,
        "annual_return_pct": 6.0, "inflation_pct": 3.0,
    }
    base.update(overrides)
    return base


class TestLifeExpectancyMethod:
    def test_year_one_withdrawal_is_balance_over_remaining_years(self):
        result = act.life_expectancy_method(make_settings(retirement_age=65.0, life_expectancy_age=90.0))
        expected = result["balance_at_retirement"] / 25.0
        assert abs(result["year_one_withdrawal"] - expected) < 0.01


class TestRmdDivisor:
    def test_uses_table_value_at_known_age(self):
        assert rmd_divisor(75) == IRS_UNIFORM_LIFETIME_TABLE[75]

    def test_below_72_uses_72_divisor(self):
        assert rmd_divisor(50) == IRS_UNIFORM_LIFETIME_TABLE[72]

    def test_above_table_max_uses_final_entry(self):
        assert rmd_divisor(150) == IRS_UNIFORM_LIFETIME_TABLE[max(IRS_UNIFORM_LIFETIME_TABLE)]


class TestIrsRmdSchedule:
    def test_starts_at_72_when_retirement_is_earlier(self):
        result = act.irs_rmd_schedule(make_settings(retirement_age=60.0, life_expectancy_age=90.0))
        assert result["start_age"] == 72

    def test_starts_at_retirement_age_when_later_than_72(self):
        result = act.irs_rmd_schedule(make_settings(retirement_age=75.0, life_expectancy_age=90.0))
        assert result["start_age"] == 75

    def test_schedule_covers_expected_number_of_years(self):
        result = act.irs_rmd_schedule(make_settings(retirement_age=72.0, life_expectancy_age=80.0))
        assert result["schedule"][0]["age"] == 72
        assert result["schedule"][-1]["age"] <= 80

    def test_rmd_as_share_of_balance_rises_with_age(self):
        """The IRS divisor strictly decreases with age, so RMD/balance
        (= 1/divisor) must strictly increase every year — the ABSOLUTE
        dollar RMD isn't guaranteed to rise too, since the balance itself
        also shrinks each year from the prior withdrawal, and that effect
        can outpace the divisor's own shrink rate."""
        result = act.irs_rmd_schedule(make_settings(retirement_age=72.0, life_expectancy_age=80.0, annual_return_pct=0.0))
        shares = [row["rmd"] / row["balance_before"] for row in result["schedule"]]
        assert shares == sorted(shares)
        assert shares[-1] > shares[0]


class TestGompertzMakeham:
    def test_survival_probability_between_zero_and_one(self):
        result = act.gompertz_makeham(make_settings(current_age=35.0, life_expectancy_age=90.0))
        assert 0.0 <= result["survival_probability_to_life_expectancy"] <= 1.0

    def test_survival_probability_decreases_for_older_target_age(self):
        younger_target = act.gompertz_makeham(make_settings(current_age=35.0, life_expectancy_age=80.0))
        older_target = act.gompertz_makeham(make_settings(current_age=35.0, life_expectancy_age=100.0))
        assert older_target["survival_probability_to_life_expectancy"] < younger_target["survival_probability_to_life_expectancy"]

    def test_implied_median_lifespan_is_after_current_age(self):
        result = act.gompertz_makeham(make_settings(current_age=35.0))
        assert result["implied_median_lifespan"] > 35.0
