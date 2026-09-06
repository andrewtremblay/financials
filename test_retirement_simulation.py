"""
Tests for retirement_simulation.py — category 2 of the Retirement Planning
spec (Monte Carlo, Bootstrapping, Historical Simulation, Regime-Switching).

Run with: uv run pytest test_retirement_simulation.py -v
"""
import retirement_simulation as sim


def make_settings(**overrides):
    base = {
        "current_age": 65.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
        "current_portfolio_balance": 1_000_000.0, "annual_savings": 0.0,
        "annual_return_pct": 7.0, "inflation_pct": 3.0, "withdrawal_rate_pct": 4.0,
    }
    base.update(overrides)
    return base


class TestSimulateWithdrawalSequence:
    def test_succeeds_with_generous_balance_and_flat_positive_returns(self):
        assert sim._simulate_withdrawal_sequence(1_000_000.0, 1.0, 2.0, [5.0] * 30) is True

    def test_fails_with_high_withdrawal_and_flat_zero_returns(self):
        assert sim._simulate_withdrawal_sequence(1_000_000.0, 50.0, 2.0, [0.0] * 30) is False


class TestMonteCarlo:
    def test_deterministic_given_a_fixed_seed(self):
        a = sim.monte_carlo(make_settings(), trials=200, seed=1)
        b = sim.monte_carlo(make_settings(), trials=200, seed=1)
        assert a == b

    def test_success_rate_is_between_0_and_100(self):
        result = sim.monte_carlo(make_settings(), trials=200)
        assert 0.0 <= result["success_rate_pct"] <= 100.0

    def test_higher_withdrawal_rate_lowers_success_rate(self):
        conservative = sim.monte_carlo(make_settings(withdrawal_rate_pct=2.0), trials=500, seed=7)
        aggressive = sim.monte_carlo(make_settings(withdrawal_rate_pct=10.0), trials=500, seed=7)
        assert aggressive["success_rate_pct"] <= conservative["success_rate_pct"]


class TestBootstrapping:
    def test_deterministic_given_a_fixed_seed(self):
        a = sim.bootstrapping(make_settings(), trials=200, seed=1)
        b = sim.bootstrapping(make_settings(), trials=200, seed=1)
        assert a == b

    def test_success_rate_is_between_0_and_100(self):
        result = sim.bootstrapping(make_settings(), trials=200)
        assert 0.0 <= result["success_rate_pct"] <= 100.0


class TestHistoricalSimulation:
    def test_tests_multiple_non_overlapping_length_windows(self):
        result = sim.historical_simulation(make_settings(retirement_age=65.0, life_expectancy_age=90.0))
        assert result["windows_tested"] > 0
        assert result["years_simulated"] == 25

    def test_success_rate_is_between_0_and_100(self):
        result = sim.historical_simulation(make_settings())
        assert 0.0 <= result["success_rate_pct"] <= 100.0

    def test_zero_windows_when_horizon_exceeds_available_data(self):
        result = sim.historical_simulation(make_settings(retirement_age=65.0, life_expectancy_age=65.0 + 500))
        assert result["windows_tested"] == 0
        assert result["success_rate_pct"] is None


class TestRegimeSwitching:
    def test_deterministic_given_a_fixed_seed(self):
        a = sim.regime_switching(make_settings(), trials=200, seed=1)
        b = sim.regime_switching(make_settings(), trials=200, seed=1)
        assert a == b

    def test_growth_mean_exceeds_recession_mean(self):
        result = sim.regime_switching(make_settings(), trials=100)
        assert result["growth_mean_return_pct"] > result["recession_mean_return_pct"]

    def test_transition_probabilities_are_valid_percentages(self):
        result = sim.regime_switching(make_settings(), trials=100)
        assert 0.0 <= result["prob_stay_in_growth_pct"] <= 100.0
        assert 0.0 <= result["prob_recover_from_recession_pct"] <= 100.0
