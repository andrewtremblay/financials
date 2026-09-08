"""
Tests for overrides.py.

Run with: uv run pytest test_overrides.py -v
"""
import importlib

import pytest

import overrides


@pytest.fixture(autouse=True)
def isolated_overrides_file(tmp_path, monkeypatch):
    """Every test gets its own overrides file — never touch the real one."""
    monkeypatch.setattr(overrides, "OVERRIDES_FILE", tmp_path / "category_overrides.json")


class TestTransactionOverrides:
    def test_no_override_returns_none(self):
        assert overrides.lookup_transaction_override("txn-1") is None

    def test_none_transaction_id_returns_none(self):
        assert overrides.lookup_transaction_override(None) is None

    def test_add_then_lookup(self):
        overrides.add_transaction_override("txn-1", "GIFTS")
        assert overrides.lookup_transaction_override("txn-1") == "GIFTS"
        assert overrides.lookup_transaction_override("txn-2") is None

    def test_overwrite_existing_override(self):
        overrides.add_transaction_override("txn-1", "GIFTS")
        overrides.add_transaction_override("txn-1", "GROCERIES")
        assert overrides.lookup_transaction_override("txn-1") == "GROCERIES"

    def test_no_in_memory_cache_across_reload(self, tmp_path, monkeypatch):
        """The writer (API process) and reader (daily plaid_sync.py) are
        different processes — a stale in-memory cache would silently ignore
        overrides written after the reading process started. Simulate a
        separate process by reloading the module and confirming it still
        sees data written before the reload."""
        overrides.add_transaction_override("txn-1", "GIFTS")
        importlib.reload(overrides)
        monkeypatch.setattr(overrides, "OVERRIDES_FILE", tmp_path / "category_overrides.json")
        assert overrides.lookup_transaction_override("txn-1") == "GIFTS"


class TestMerchantRules:
    def test_no_rules_returns_none(self):
        assert overrides.lookup_merchant_rule("STARBUCKS #123") is None

    def test_substring_match_is_case_insensitive(self):
        overrides.add_merchant_rule("STARBUCKS", "FOOD RESTAURANTS")
        assert overrides.lookup_merchant_rule("STARBUCKS #4521 BOSTON MA") == "FOOD RESTAURANTS"
        assert overrides.lookup_merchant_rule("starbucks downtown") == "FOOD RESTAURANTS"
        assert overrides.lookup_merchant_rule("Dunkin") is None

    def test_exact_match_requires_full_string(self):
        overrides.add_merchant_rule("STARBUCKS", "FOOD RESTAURANTS", match_type="exact")
        assert overrides.lookup_merchant_rule("STARBUCKS") == "FOOD RESTAURANTS"
        assert overrides.lookup_merchant_rule("starbucks") == "FOOD RESTAURANTS"  # case-insensitive
        assert overrides.lookup_merchant_rule("STARBUCKS #4521") is None

    def test_regex_match(self):
        overrides.add_merchant_rule(r"^AMZN.*MKTP", "RETAIL", match_type="regex")
        assert overrides.lookup_merchant_rule("AMZN MKTP US*AB12CD") == "RETAIL"
        assert overrides.lookup_merchant_rule("NOT AMZN MKTP") is None  # anchored at start

    def test_invalid_match_type_raises(self):
        with pytest.raises(ValueError):
            overrides.add_merchant_rule("FOO", "BAR", match_type="fuzzy")

    def test_first_match_wins(self):
        overrides.add_merchant_rule("SHOP", "RETAIL")
        overrides.add_merchant_rule("COFFEE SHOP", "FOOD RESTAURANTS")
        assert overrides.lookup_merchant_rule("COFFEE SHOP DOWNTOWN") == "RETAIL"  # first rule matches first

    def test_list_and_remove(self):
        rule = overrides.add_merchant_rule("STARBUCKS", "FOOD RESTAURANTS")
        assert len(overrides.list_merchant_rules()) == 1
        assert overrides.remove_merchant_rule(rule["id"]) is True
        assert overrides.list_merchant_rules() == []

    def test_remove_nonexistent_rule_returns_false(self):
        assert overrides.remove_merchant_rule("nonexistent") is False

    def test_amount_scoped_rule_requires_matching_amount(self):
        overrides.add_merchant_rule("VENMO", "HOME PROFESSIONAL CLEANING", amount=120.00)
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=120.00) == "HOME PROFESSIONAL CLEANING"
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=45.00) is None
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=None) is None

    def test_amount_scoped_rule_tolerates_cent_rounding(self):
        overrides.add_merchant_rule("VENMO", "HOME PROFESSIONAL CLEANING", amount=120.00)
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=120.004) == "HOME PROFESSIONAL CLEANING"

    def test_rule_without_amount_matches_any_amount(self):
        overrides.add_merchant_rule("VENMO", "TRANSFERS")
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=120.00) == "TRANSFERS"
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=None) == "TRANSFERS"

    def test_amount_scoped_rule_does_not_shadow_generic_rule(self):
        """The generic (no-amount) rule is checked in list order — an
        amount-scoped rule added first for a specific amount should not
        block a later generic rule from matching other amounts."""
        overrides.add_merchant_rule("VENMO", "HOME PROFESSIONAL CLEANING", amount=120.00)
        overrides.add_merchant_rule("VENMO", "TRANSFERS")
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=120.00) == "HOME PROFESSIONAL CLEANING"
        assert overrides.lookup_merchant_rule("VENMO PAYMENT", amount=45.00) == "TRANSFERS"


class TestIgnoredTransactions:
    def test_note_stored_and_retrievable(self):
        overrides.add_transaction_override("txn-1", "IGNORED", "duplicate charge, refunded")
        ignored = overrides.list_ignored_transactions()
        assert ignored["txn-1"]["note"] == "duplicate charge, refunded"

    def test_note_defaults_to_none(self):
        overrides.add_transaction_override("txn-1", "IGNORED")
        assert overrides.list_ignored_transactions()["txn-1"]["note"] is None

    def test_list_ignored_excludes_non_ignored_overrides(self):
        overrides.add_transaction_override("txn-1", "IGNORED", "reason")
        overrides.add_transaction_override("txn-2", "GIFTS")
        ignored = overrides.list_ignored_transactions()
        assert "txn-1" in ignored
        assert "txn-2" not in ignored

    def test_update_ignored_note(self):
        overrides.add_transaction_override("txn-1", "IGNORED", "first reason")
        assert overrides.update_ignored_note("txn-1", "corrected reason") is True
        assert overrides.list_ignored_transactions()["txn-1"]["note"] == "corrected reason"
        # category/set_at untouched by a note-only update.
        assert overrides.lookup_transaction_override("txn-1") == "IGNORED"

    def test_update_ignored_note_on_non_ignored_transaction_fails(self):
        overrides.add_transaction_override("txn-1", "GIFTS")
        assert overrides.update_ignored_note("txn-1", "some note") is False

    def test_update_ignored_note_on_nonexistent_transaction_fails(self):
        assert overrides.update_ignored_note("nonexistent", "some note") is False


class TestPrecedence:
    def test_transaction_override_beats_merchant_rule(self):
        """categorize.py checks transaction override first, then merchant
        rule — this test documents the intended precedence at the lookup
        level (categorize.py's actual `or` chain is exercised elsewhere)."""
        overrides.add_merchant_rule("STARBUCKS", "FOOD RESTAURANTS")
        overrides.add_transaction_override("txn-1", "GIFTS")
        # A caller checking transaction override first would get GIFTS even
        # though the merchant rule would say FOOD RESTAURANTS for this description.
        assert overrides.lookup_transaction_override("txn-1") == "GIFTS"
        assert overrides.lookup_merchant_rule("STARBUCKS #123") == "FOOD RESTAURANTS"
