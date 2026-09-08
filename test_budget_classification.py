"""
Tests for budget_classification.py and custom_budget_classification.py — the
Need/Want/Housing/Debt tagging used by budget_rules.py.

Run with: uv run pytest test_budget_classification.py -v
"""
import pytest

import budget_classification
import custom_budget_classification


@pytest.fixture(autouse=True)
def isolated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_budget_classification, "CUSTOM_BUDGET_CLASSIFICATION_FILE", tmp_path / "custom_budget_classification.json")


class TestStaticDefaults:
    def test_known_line_item_uses_static_default(self):
        assert budget_classification.classify_line_item("DAILY LIVING", "Groceries") == {"budget_type": "need", "housing": False, "debt": False}
        assert budget_classification.classify_line_item("DAILY LIVING", "Dining Out") == {"budget_type": "want", "housing": False, "debt": False}

    def test_mortgage_is_need_housing_and_debt(self):
        tag = budget_classification.classify_line_item("HOME", "Mortgage (12 Warren)")
        assert tag == {"budget_type": "need", "housing": True, "debt": True}

    def test_unknown_line_item_falls_back_to_want(self):
        assert budget_classification.classify_line_item("DAILY LIVING", "Some New Custom Category") == budget_classification.FALLBACK_BUDGET_TYPE


class TestOverrides:
    def test_override_wins_over_static_default(self):
        custom_budget_classification.set_override("DAILY LIVING", "Groceries", "want", False, False)
        assert budget_classification.classify_line_item("DAILY LIVING", "Groceries")["budget_type"] == "want"

    def test_override_applies_to_unknown_line_item(self):
        custom_budget_classification.set_override("DAILY LIVING", "Pet Supplies", "need", False, False)
        assert budget_classification.classify_line_item("DAILY LIVING", "Pet Supplies")["budget_type"] == "need"

    def test_invalid_budget_type_rejected(self):
        with pytest.raises(ValueError):
            custom_budget_classification.set_override("HOME", "Other", "sometimes", False, False)

    def test_all_classifications_merges_overrides_and_defaults(self):
        custom_budget_classification.set_override("DAILY LIVING", "Groceries", "want", False, False)
        keys = [("DAILY LIVING", "Groceries"), ("DAILY LIVING", "Dining Out")]
        result = budget_classification.all_classifications(keys)
        assert result[("DAILY LIVING", "Groceries")]["budget_type"] == "want"
        assert result[("DAILY LIVING", "Dining Out")]["budget_type"] == "want"  # static default, unaffected
