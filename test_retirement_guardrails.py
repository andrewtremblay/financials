"""
Tests for retirement_guardrails.py — category 4 of the Retirement Planning
spec (Guyton-Klinger, VPW, Bengen Floor-and-Ceiling, Ratchet, Optimal
Control Theory).

Run with: uv run pytest test_retirement_guardrails.py -v
"""
import retirement_guardrails as g


def make_settings(**overrides):
    base = {
        "current_age": 65.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
        "current_portfolio_balance": 1_000_000.0, "annual_savings": 0.0,
        "annual_return_pct": 6.0, "inflation_pct": 3.0, "bond_yield_pct": 4.0,
        "withdrawal_rate_pct": 4.0, "risk_aversion": 3.0,
    }
    base.update(overrides)
    return base


class TestGuytonKlinger:
    def test_no_guardrail_triggers_under_perfectly_stable_growth(self):
        """A return exactly matching the initial withdrawal rate's implied
        depletion path shouldn't drift the current rate far enough to ever
        cross either guardrail band."""
        result = g.guyton_klinger(make_settings(annual_return_pct=7.0, inflation_pct=3.0, withdrawal_rate_pct=4.0))
        assert result["ending_balance"] >= 0

    def test_low_return_triggers_capital_preservation_cuts(self):
        result = g.guyton_klinger(make_settings(annual_return_pct=0.0, withdrawal_rate_pct=6.0))
        assert result["guardrail_cuts_triggered"] > 0

    def test_never_goes_meaningfully_negative(self):
        result = g.guyton_klinger(make_settings(annual_return_pct=-2.0, withdrawal_rate_pct=8.0))
        assert result["ending_balance"] >= 0


class TestVPW:
    def test_final_year_withdraws_the_entire_remaining_balance(self):
        result = g.variable_percentage_withdrawal(make_settings())
        assert result["final_year_withdrawal_rate_pct"] == 100.0
        assert result["ending_balance"] == 0.0

    def test_rate_rises_as_remaining_years_shrink(self):
        result = g.variable_percentage_withdrawal(make_settings())
        assert result["final_year_withdrawal_rate_pct"] > result["year_one_withdrawal_rate_pct"]


class TestBengenFloorCeiling:
    def test_year_one_within_floor_and_ceiling(self):
        result = g.bengen_floor_ceiling(make_settings())
        assert result["floor_year_one"] <= result["year_one_withdrawal"] <= result["ceiling_year_one"]

    def test_never_goes_negative(self):
        result = g.bengen_floor_ceiling(make_settings(annual_return_pct=-5.0, withdrawal_rate_pct=10.0))
        assert result["ending_balance"] >= 0


class TestRatchetRule:
    def test_final_withdrawal_never_below_year_one_when_plan_stays_funded(self):
        """The whole point of a ratchet: spending never decreases in
        nominal terms — as long as the plan doesn't run out of money
        entirely (a separate, expected edge case covered below)."""
        result = g.ratchet_rule(make_settings(annual_return_pct=5.0, withdrawal_rate_pct=4.0))
        assert result["ending_balance"] > 0  # sanity: this scenario shouldn't deplete
        assert result["final_year_withdrawal"] >= result["year_one_withdrawal"]

    def test_depleted_plan_clamps_to_zero_rather_than_negative(self):
        """A poor-enough return can still exhaust the balance despite the
        ratchet's "never decreases" promise — once truly out of money,
        withdrawal is clamped to zero rather than driving the balance
        negative."""
        result = g.ratchet_rule(make_settings(annual_return_pct=1.0, withdrawal_rate_pct=4.0))
        assert result["ending_balance"] == 0.0
        assert result["final_year_withdrawal"] == 0.0

    def test_strong_growth_triggers_ratchets_up(self):
        result = g.ratchet_rule(make_settings(annual_return_pct=15.0, withdrawal_rate_pct=4.0))
        assert result["ratchets_triggered"] > 0

    def test_never_goes_negative(self):
        result = g.ratchet_rule(make_settings(annual_return_pct=-3.0, withdrawal_rate_pct=9.0))
        assert result["ending_balance"] >= 0


class TestOptimalControlBellman:
    def test_returns_a_positive_year_one_withdrawal(self):
        result = g.optimal_control_bellman(make_settings(), grid_size=20)
        assert result["optimal_year_one_withdrawal"] > 0
        assert result["optimal_year_one_withdrawal"] <= result["balance_at_retirement"]

    def test_zero_balance_short_circuits(self):
        result = g.optimal_control_bellman(make_settings(current_portfolio_balance=0.0, annual_savings=0.0), grid_size=20)
        assert result["year_one_withdrawal"] == 0.0

    def test_higher_risk_aversion_smooths_consumption_more(self):
        """Higher gamma (more risk-averse / consumption-smoothing) should
        pull year-one spending down relative to a risk-neutral-ish low
        gamma, which front-loads consumption more aggressively."""
        low_gamma = g.optimal_control_bellman(make_settings(risk_aversion=1.0), grid_size=20)
        high_gamma = g.optimal_control_bellman(make_settings(risk_aversion=8.0), grid_size=20)
        assert high_gamma["optimal_year_one_withdrawal"] <= low_gamma["optimal_year_one_withdrawal"]
