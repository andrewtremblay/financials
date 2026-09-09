"""
Tests for sheets_sync.py's aggregate_month/_line_item_cell.

Run with: uv run pytest test_sheets_sync.py -v
"""
import pandas as pd
import pytest

import custom_categories
import sheets_sync
from sheets_sync import _all_line_item_cells, _line_item_cell, aggregate_month, aggregate_year


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


class FakeWorksheet:
    """Minimal stand-in for a gspread Worksheet -- only what aggregate_year's
    _read_tab_values needs: batch_get(refs) -> [[[value]] or [] per ref]."""

    def __init__(self, title, cell_values):
        self.title = title
        self.cell_values = cell_values

    def batch_get(self, refs, value_render_option=None):
        return [[[self.cell_values[ref]]] if ref in self.cell_values else [] for ref in refs]


class FakeSpreadsheet:
    def __init__(self, worksheets):
        self._worksheets = worksheets

    def worksheets(self):
        return self._worksheets


class TestAggregateYear:
    def test_sums_projected_and_actual_across_months(self):
        # D4 = Take Home Salary (Zus): row from budget_schema.BUDGET_SECTIONS.
        july = FakeWorksheet("July 2026", {"C4": 9000, "D4": 9865.38})
        august = FakeWorksheet("August 2026", {"C4": 9000, "D4": 9865.38})
        spreadsheet = FakeSpreadsheet([july, august])

        projected_totals, actual_totals, missing_tabs = aggregate_year(spreadsheet, ["2026-07", "2026-08"])

        assert projected_totals[("D", 4)] == 18000.0
        assert actual_totals[("D", 4)] == 19730.76
        assert missing_tabs == []

    def test_missing_tab_contributes_zero_and_is_reported(self):
        august = FakeWorksheet("August 2026", {"D4": 9865.38})
        spreadsheet = FakeSpreadsheet([august])

        projected_totals, actual_totals, missing_tabs = aggregate_year(spreadsheet, ["2026-07", "2026-08"])

        assert actual_totals[("D", 4)] == 9865.38
        assert missing_tabs == ["July 2026"]

    def test_covers_every_physical_line_item_cell(self):
        # Sanity check that the row layout helper used to drive both reading
        # and writing covers all sections, including "Other" catch-all rows.
        cells = _all_line_item_cells()
        labels = {label for label, _, _, _ in cells}
        assert "Other" in labels
        assert "Take Home Salary (Zus)" in labels
        assert "Mortgage (12 Warren)" in labels
