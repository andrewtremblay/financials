"""
Tests for sheets_sync.py's aggregate_month/_line_item_cell.

Run with: uv run pytest test_sheets_sync.py -v
"""
import pandas as pd
import pytest

import custom_categories
import sheets_sync
from sheets_sync import _line_item_cell, aggregate_month


@pytest.fixture(autouse=True)
def isolated_custom_categories_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")


def txn(date, description, amount, category, year_month=None, account="Test Bank checking 0000", transaction_id=None):
    return {
        "raw_transaction": str([date, description, amount]),
        "description": description,
        "date": date,
        "amount": amount,
        "category": category,
        "transaction_id": transaction_id,
        "year_month": year_month or date[:7],
        "account": account,
    }


COLUMNS = ["raw_transaction", "description", "date", "amount", "category", "transaction_id", "year_month", "account"]


def make_df(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


class TestLineItemCell:
    def test_known_expense_line_item(self):
        assert _line_item_cell("HOME", "Mortgage (12 Warren)") is not None

    def test_known_income_line_item(self):
        assert _line_item_cell("income", "Take Home Salary (Zus)") is not None

    def test_unknown_line_item_returns_none(self):
        # No physical Sheet row exists for a category invented after the
        # Sheet's row layout was fixed -- must return None, not raise.
        assert _line_item_cell("savings", "Some Brand New Custom Category") is None

    def test_unknown_expense_other_row_when_section_has_none(self):
        # TRANSPORTATION has no "Other" row in the Sheet at all.
        assert _line_item_cell("TRANSPORTATION", "Other") is None


class TestAggregateMonthWithCustomCategories:
    def test_custom_category_routes_to_needs_review_not_a_crash(self, monkeypatch, tmp_path):
        """A category created through the dashboard's "add a new category"
        flow (custom_categories.py) has no physical Sheet row -- aggregate_month
        must flag it via needs_review instead of raising a bare KeyError
        (2026-09-08 regression: crashed the entire monthly sync on "James
        Education Fund")."""
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")
        custom_categories.add_custom_category("JAMES EDUCATION FUND", "savings", "James Education Fund")
        df = make_df([
            txn("2026-07-01", "529 contribution", 100.0, "JAMES EDUCATION FUND", transaction_id="txn-1"),
        ])
        cell_values, cell_notes, needs_review = aggregate_month(df, "2026-07")
        assert cell_values == {}
        assert len(needs_review) == 1
        key = next(iter(needs_review))
        assert "James Education Fund" in key
        amount, count = needs_review[key]
        assert amount == 100.0
        assert count == 1

    def test_known_category_still_writes_a_cell(self):
        df = make_df([
            txn("2026-07-01", "Stop & Shop", 80.0, "GROCERY", transaction_id="txn-1"),
        ])
        cell_values, cell_notes, needs_review = aggregate_month(df, "2026-07")
        assert len(cell_values) == 1
        assert needs_review == {}
