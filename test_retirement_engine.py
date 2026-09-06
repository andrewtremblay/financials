"""
Tests for retirement_engine.py — the orchestrator assembling every
retirement_*.py model into one uniform, categorized list.

Run with: uv run pytest test_retirement_engine.py -v
"""
import retirement_engine as engine


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


def test_every_model_has_a_unique_key():
    keys = [m.key for m in engine.MODELS]
    assert len(keys) == len(set(keys))


def test_every_model_belongs_to_a_known_category():
    for m in engine.MODELS:
        assert m.category in engine.CATEGORIES


def test_at_least_26_models_covering_all_7_categories():
    assert len(engine.MODELS) >= 26
    assert {m.category for m in engine.MODELS} == set(engine.CATEGORIES)


def test_compute_all_returns_one_entry_per_model_with_no_errors():
    results = engine.compute_all(make_settings())
    assert len(results) == len(engine.MODELS)
    for r in results:
        assert "error" not in r["result"], f"{r['key']} failed: {r['result']}"


def test_compute_all_survives_all_zero_settings():
    """A brand-new user who hasn't filled in the settings panel yet gets
    all-zero defaults — every model must degrade gracefully (zeros/None),
    never raise."""
    zero_settings = {k: 0.0 for k in make_settings()}
    zero_settings["current_age"] = 30.0
    zero_settings["retirement_age"] = 65.0
    zero_settings["life_expectancy_age"] = 90.0
    results = engine.compute_all(zero_settings)
    assert len(results) == len(engine.MODELS)
