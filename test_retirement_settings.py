"""
Tests for retirement_settings.py.

Run with: uv run pytest test_retirement_settings.py -v
"""
import pytest

import retirement_settings


@pytest.fixture(autouse=True)
def isolated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(retirement_settings, "RETIREMENT_SETTINGS_FILE", tmp_path / "retirement_settings.json")


def test_get_settings_returns_defaults_when_unset():
    assert retirement_settings.get_settings() == retirement_settings.DEFAULT_SETTINGS


def test_update_settings_persists_and_merges():
    retirement_settings.update_settings({"current_age": 40.0, "retirement_age": 62.0})
    result = retirement_settings.get_settings()
    assert result["current_age"] == 40.0
    assert result["retirement_age"] == 62.0
    # Untouched fields keep their default.
    assert result["inflation_pct"] == retirement_settings.DEFAULT_SETTINGS["inflation_pct"]


def test_update_settings_survives_reload(tmp_path, monkeypatch):
    """Simulates a fresh process (same technique as
    test_overrides.py's test_no_in_memory_cache_across_reload): the
    persisted file, not any in-memory state, must be the source of truth."""
    retirement_settings.update_settings({"current_portfolio_balance": 500000.0})
    store_path = retirement_settings.RETIREMENT_SETTINGS_FILE
    import importlib
    importlib.reload(retirement_settings)
    monkeypatch.setattr(retirement_settings, "RETIREMENT_SETTINGS_FILE", store_path)
    assert retirement_settings.get_settings()["current_portfolio_balance"] == 500000.0


def test_unknown_setting_key_rejected():
    with pytest.raises(ValueError):
        retirement_settings.update_settings({"not_a_real_field": 1.0})


def test_partial_update_does_not_clobber_other_fields():
    retirement_settings.update_settings({"current_age": 45.0})
    retirement_settings.update_settings({"retirement_age": 60.0})
    result = retirement_settings.get_settings()
    assert result["current_age"] == 45.0
    assert result["retirement_age"] == 60.0
