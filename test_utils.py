"""
Tests for utility functions in utils.py (excluding fmt_sankeymatic, which is
covered by test_fmt_sankeymatic.py).

Run with: uv run pytest test_utils.py -v
"""
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

# Patch heavy dependencies before importing utils
for mod in [
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.output_parsers",
    "docling",
    "docling.document_converter",
    "memo",
]:
    sys.modules[mod] = MagicMock()

import utils  # noqa: E402
from utils import (  # noqa: E402
    IGNORE_CATEGORY,
    clean_numeric_amount,
    count_categories,
    extract_date_and_amount_from_transaction,
    fmt_capitalize,
    load_local_category_hints,
)


# ---------------------------------------------------------------------------
# fmt_capitalize
# ---------------------------------------------------------------------------

class TestFmtCapitalize:
    def test_single_word(self):
        assert fmt_capitalize("FOOD") == "Food"

    def test_multi_word_underscores(self):
        assert fmt_capitalize("HOME_REPAIR") == "Home Repair"

    def test_three_word(self):
        assert fmt_capitalize("CREDIT_CARD_PAYMENT") == "Credit Card Payment"

    def test_atm_withdrawal_uses_map(self):
        assert fmt_capitalize("ATM_WITHDRAWAL") == "ATM Withdrawal"

    def test_mbta_uses_map(self):
        assert fmt_capitalize("MBTA") == "MBTA"

    def test_chatgpt_uses_map(self):
        assert fmt_capitalize("CHATGPT") == "ChatGPT"

    def test_already_lowercase_word(self):
        # Treats each segment independently; input is always uppercase by convention
        assert fmt_capitalize("gas") == "Gas"

    def test_underscore_hierarchy_becomes_spaced_title_case(self):
        assert fmt_capitalize("FOOD_RESTAURANTS") == "Food Restaurants"


# ---------------------------------------------------------------------------
# clean_numeric_amount
# ---------------------------------------------------------------------------

class TestCleanNumericAmount:
    def _dummy_row(self):
        row = MagicMock()
        row.raw_transaction = "dummy transaction"
        return row

    def test_string_integer(self):
        assert clean_numeric_amount("100", self._dummy_row()) == 100.0

    def test_string_with_decimal(self):
        assert clean_numeric_amount("45.67", self._dummy_row()) == 45.67

    def test_string_with_comma(self):
        assert clean_numeric_amount("1,234.56", self._dummy_row()) == 1234.56

    def test_float_value(self):
        assert clean_numeric_amount(50.0, self._dummy_row()) == 50.0

    def test_int_value(self):
        assert clean_numeric_amount(99, self._dummy_row()) == 99

    def test_nan_float_returns_zero(self):
        assert clean_numeric_amount(float("nan"), self._dummy_row()) == 0

    def test_unparseable_string_raises(self):
        # clean_numeric_amount does not catch ValueError from float(); it propagates
        with pytest.raises(ValueError):
            clean_numeric_amount("not_a_number", self._dummy_row())


# ---------------------------------------------------------------------------
# extract_date_and_amount_from_transaction
# ---------------------------------------------------------------------------

class TestExtractDateAndAmount:
    def test_basic_positive(self):
        result = extract_date_and_amount_from_transaction("01/15 STARBUCKS 4.50")
        assert result == ("01/15", "4.50")

    def test_negative_amount(self):
        result = extract_date_and_amount_from_transaction("03/22 REFUND -25.00")
        assert result == ("03/22", "-25.00")

    def test_amount_with_comma(self):
        result = extract_date_and_amount_from_transaction("12/01 BIG PURCHASE 1,234.56")
        assert result == ("12/01", "1,234.56")

    def test_no_date_returns_none(self):
        result = extract_date_and_amount_from_transaction("SOME DESCRIPTION 45.00")
        assert result is None

    def test_no_amount_returns_none(self):
        result = extract_date_and_amount_from_transaction("01/15 DESCRIPTION ONLY")
        assert result is None

    def test_empty_string_returns_none(self):
        result = extract_date_and_amount_from_transaction("")
        assert result is None


# ---------------------------------------------------------------------------
# count_categories
# ---------------------------------------------------------------------------

class TestCountCategories:
    def _make_df(self, rows):
        """rows: list of (category, amount) tuples."""
        return pd.DataFrame(rows, columns=["category", "amount"])

    def test_simple_accumulation(self):
        df = self._make_df([("FOOD", 50), ("FOOD", 30)])
        data = count_categories(df, {})
        assert data["FOOD"] == 80

    def test_multiple_categories(self):
        df = self._make_df([("FOOD", 100), ("GAS", 40)])
        data = count_categories(df, {})
        assert data["FOOD"] == 100
        assert data["GAS"] == 40

    def test_ignore_category_skipped(self):
        for ignored in IGNORE_CATEGORY:
            df = self._make_df([(ignored, 500)])
            data = count_categories(df, {})
            assert ignored not in data

    def test_subcategory_space_notation_populates_map(self):
        # "FOOD RESTAURANTS" means RESTAURANTS is a child of FOOD
        df = self._make_df([("FOOD RESTAURANTS", 75)])
        data = count_categories(df, {})
        assert data["_map"]["RESTAURANTS"] == "FOOD"

    def test_subcategory_amount_added_to_both(self):
        df = self._make_df([("FOOD RESTAURANTS", 75)])
        data = count_categories(df, {})
        assert data["FOOD"] == 75
        assert data["RESTAURANTS"] == 75

    def test_accumulates_across_calls(self):
        df1 = self._make_df([("FOOD", 100)])
        df2 = self._make_df([("FOOD", 50)])
        data = count_categories(df1, {})
        data = count_categories(df2, data)
        assert data["FOOD"] == 150

    def test_amounts_are_rounded(self):
        df = self._make_df([("FOOD", 33.7)])
        data = count_categories(df, {})
        assert data["FOOD"] == round(33.7)

    def test_string_amount_parsed(self):
        df = self._make_df([("FOOD", "1,234.00")])
        data = count_categories(df, {})
        assert data["FOOD"] == 1234

    def test_map_initialized_if_absent(self):
        df = self._make_df([("GAS", 30)])
        data = count_categories(df, {})
        assert "_map" in data

    def test_map_preserved_across_calls(self):
        df1 = self._make_df([("FOOD RESTAURANTS", 50)])
        df2 = self._make_df([("GAS", 30)])
        data = count_categories(df1, {})
        data = count_categories(df2, data)
        assert "RESTAURANTS" in data["_map"]
        assert data["GAS"] == 30


# ---------------------------------------------------------------------------
# load_local_category_hints
# ---------------------------------------------------------------------------

class TestLoadLocalCategoryHints:
    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(utils, "LOCAL_CATEGORY_HINTS_FILE", str(tmp_path / "absent.txt"))
        assert load_local_category_hints() == ""

    def test_reads_hints_and_ignores_comments_and_blanks(self, monkeypatch, tmp_path):
        hints = tmp_path / "hints.txt"
        hints.write_text("# a comment\n\nACME is a FOOD category.\nGLOBEX is a WAGES category.\n")
        monkeypatch.setattr(utils, "LOCAL_CATEGORY_HINTS_FILE", str(hints))
        result = load_local_category_hints()
        assert "ACME is a FOOD category." in result
        assert "GLOBEX is a WAGES category." in result
        assert "#" not in result
        assert result.endswith(" ")
