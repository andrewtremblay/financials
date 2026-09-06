"""
Tests for retirement_structuring.py — category 6 of the Retirement
Planning spec (ALM, Time-Segmented Bucketing, Bond Ladder Mathematics).

Run with: uv run pytest test_retirement_structuring.py -v
"""
import retirement_structuring as struct


def make_settings(**overrides):
    base = {
        "current_age": 65.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
        "current_portfolio_balance": 1_000_000.0, "annual_savings": 0.0,
        "annual_return_pct": 6.0, "bond_yield_pct": 4.0,
        "desired_annual_spending": 60000.0, "social_security_annual": 20000.0, "pension_annual": 10000.0,
    }
    base.update(overrides)
    return base


class TestAssetLiabilityMatching:
    def test_gap_is_spending_minus_guaranteed_income(self):
        result = struct.asset_liability_matching(make_settings())
        assert result["guaranteed_income_annual"] == 30000.0
        assert result["annual_liability_gap"] == 30000.0

    def test_gap_floors_at_zero_when_guaranteed_income_covers_everything(self):
        result = struct.asset_liability_matching(make_settings(social_security_annual=100000.0, pension_annual=0.0))
        assert result["annual_liability_gap"] == 0.0
        assert result["portfolio_needed_to_fully_match_gap"] == 0.0


class TestTimeSegmentedBucketing:
    def test_buckets_sum_to_balance_at_retirement(self):
        result = struct.time_segmented_bucketing(make_settings())
        total = result["bucket_1_cash_years_1_5"] + result["bucket_2_bonds_years_6_10"] + result["bucket_3_equities_years_11_plus"]
        assert abs(total - result["balance_at_retirement"]) < 0.01

    def test_small_balance_all_goes_to_bucket_one(self):
        result = struct.time_segmented_bucketing(make_settings(
            current_portfolio_balance=100000.0, annual_savings=0.0, desired_annual_spending=60000.0,
        ))
        assert result["bucket_1_cash_years_1_5"] == result["balance_at_retirement"]
        assert result["bucket_2_bonds_years_6_10"] == 0.0
        assert result["bucket_3_equities_years_11_plus"] == 0.0


class TestBondLadder:
    def test_rungs_times_value_approximates_pool(self):
        result = struct.bond_ladder(make_settings())
        assert abs(result["number_of_rungs"] * result["value_per_rung"] - result["bond_pool"]) < 1.0

    def test_rung_count_capped_by_max_rungs(self):
        result = struct.bond_ladder(make_settings(retirement_age=65.0, life_expectancy_age=120.0), max_rungs=10)
        assert result["number_of_rungs"] == 10

    def test_short_retirement_uses_fewer_rungs(self):
        result = struct.bond_ladder(make_settings(retirement_age=65.0, life_expectancy_age=68.0))
        assert result["number_of_rungs"] == 3
