"""
Tests for untracked_income.py — date-scoped overrides for which Savings
line items count as "Untracked Income" (see budget_sankeymatic.py and
budget_rules.py).

Run with: uv run pytest test_untracked_income.py -v
"""
import pytest

import untracked_income


@pytest.fixture(autouse=True)
def isolated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(untracked_income, "UNTRACKED_INCOME_FILE", tmp_path / "untracked_income_overrides.json")


class TestDefaultFallback:
    def test_default_labels_resolve_true_with_no_rules(self):
        assert untracked_income.is_untracked_income("Retirement (401k + Match)", "2026-07") is True
        assert untracked_income.is_untracked_income("Emergency Fund", "2026-07") is True

    def test_non_default_label_resolves_false_with_no_rules(self):
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is False

    def test_none_year_month_falls_back_to_default(self):
        assert untracked_income.is_untracked_income("Emergency Fund", None) is True
        assert untracked_income.is_untracked_income("Other Savings", None) is False


class TestScopeCurrent:
    def test_current_scope_only_affects_that_month(self):
        untracked_income.add_rule("Other Savings", True, "current", "2026-07")
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is True
        assert untracked_income.is_untracked_income("Other Savings", "2026-06") is False
        assert untracked_income.is_untracked_income("Other Savings", "2026-08") is False

    def test_current_scope_can_turn_off_a_default_label(self):
        untracked_income.add_rule("Emergency Fund", False, "current", "2026-07")
        assert untracked_income.is_untracked_income("Emergency Fund", "2026-07") is False
        # Other months keep falling back to the default (still on).
        assert untracked_income.is_untracked_income("Emergency Fund", "2026-06") is True


class TestScopeCurrentAndFuture:
    def test_applies_from_that_month_onward_only(self):
        untracked_income.add_rule("Other Savings", True, "current_and_future", "2026-07")
        assert untracked_income.is_untracked_income("Other Savings", "2026-06") is False
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is True
        assert untracked_income.is_untracked_income("Other Savings", "2026-12") is True


class TestScopeAll:
    def test_applies_to_every_month_past_and_future(self):
        untracked_income.add_rule("Managed Brokerages", False, "all", "2026-07")
        assert untracked_income.is_untracked_income("Managed Brokerages", "2020-01") is False
        assert untracked_income.is_untracked_income("Managed Brokerages", "2026-07") is False
        assert untracked_income.is_untracked_income("Managed Brokerages", "2099-01") is False


class TestScopeValidation:
    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError):
            untracked_income.add_rule("Other Savings", True, "sometimes", "2026-07")


class TestMostRecentRuleWins:
    def test_newer_rule_shadows_older_overlapping_rule(self):
        untracked_income.add_rule("Other Savings", True, "all", "2026-07")
        untracked_income.add_rule("Other Savings", False, "current", "2026-07")
        # The newer, narrower rule wins for its exact month...
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is False
        # ...but the older "all" rule still applies everywhere else.
        assert untracked_income.is_untracked_income("Other Savings", "2026-08") is True


class TestListAndRemove:
    def test_list_rules_returns_everything_added(self):
        untracked_income.add_rule("Other Savings", True, "current", "2026-07")
        untracked_income.add_rule("Emergency Fund", False, "all", "2026-08")
        rules = untracked_income.list_rules()
        assert len(rules) == 2
        assert {r["label"] for r in rules} == {"Other Savings", "Emergency Fund"}

    def test_remove_rule_reverts_to_next_resolution(self):
        rule = untracked_income.add_rule("Other Savings", True, "current", "2026-07")
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is True
        assert untracked_income.remove_rule(rule["id"]) is True
        assert untracked_income.is_untracked_income("Other Savings", "2026-07") is False  # back to default (off)

    def test_remove_nonexistent_rule_returns_false(self):
        assert untracked_income.remove_rule("nonexistent") is False


class TestBreakdownForMonth:
    def _li(self, label, actual):
        return {"label": label, "actual": actual}

    def test_breakdown_includes_only_untracked_positive_items(self):
        items = [
            self._li("Retirement (401k + Match)", 1136.0),
            self._li("Emergency Fund", 500.0),
            self._li("Other Savings", 200.0),  # not untracked by default
        ]
        breakdown = untracked_income.breakdown_for_month(items, "2026-07")
        assert breakdown == {"Retirement (401k + Match)": 1136.0, "Emergency Fund": 500.0}

    def test_breakdown_excludes_zero_or_negative_amounts(self):
        items = [self._li("Emergency Fund", 0.0)]
        assert untracked_income.breakdown_for_month(items, "2026-07") == {}

    def test_breakdown_respects_custom_rules(self):
        untracked_income.add_rule("Other Savings", True, "all", "2026-07")
        items = [self._li("Other Savings", 300.0)]
        assert untracked_income.breakdown_for_month(items, "2026-07") == {"Other Savings": 300.0}
