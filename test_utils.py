"""Unit tests for pure helper functions in utils.py.

Heavy imports (LangChain, Docling, memo) are mocked in conftest.py, so importing
utils here only exercises pandas + the standard library.
"""
from types import SimpleNamespace

import pandas as pd

import utils
from utils import (
    clean_numeric_amount,
    count_categories,
    extract_date_and_amount_from_transaction,
    fmt_capitalize,
    load_local_category_hints,
)


class TestFmtCapitalize:
    def test_special_cases_from_map(self):
        assert fmt_capitalize("ATM_WITHDRAWAL") == "ATM Withdrawal"
        assert fmt_capitalize("CHATGPT") == "ChatGPT"
        assert fmt_capitalize("MBTA") == "MBTA"

    def test_single_word(self):
        assert fmt_capitalize("GAS") == "Gas"
        assert fmt_capitalize("food") == "Food"

    def test_underscore_hierarchy_becomes_spaced_title_case(self):
        assert fmt_capitalize("FOOD_RESTAURANTS") == "Food Restaurants"


class TestCleanNumericAmount:
    def _row(self):
        return SimpleNamespace(raw_transaction="some transaction")

    def test_string_with_commas(self):
        assert clean_numeric_amount("1,234.56", self._row()) == 1234.56

    def test_plain_numeric_string(self):
        assert clean_numeric_amount("100", self._row()) == 100.0

    def test_float_and_int_pass_through(self):
        assert clean_numeric_amount(12.5, self._row()) == 12.5
        assert clean_numeric_amount(100, self._row()) == 100

    def test_nan_float_becomes_zero(self):
        assert clean_numeric_amount(float("nan"), self._row()) == 0


class TestExtractDateAndAmount:
    def test_positive_amount(self):
        assert extract_date_and_amount_from_transaction("01/15 STORE 1,234.56") == (
            "01/15",
            "1,234.56",
        )

    def test_negative_amount(self):
        assert extract_date_and_amount_from_transaction("12/31 FOO -45.00") == (
            "12/31",
            "-45.00",
        )

    def test_no_match_returns_none(self):
        assert extract_date_and_amount_from_transaction("no date or amount here") is None


class TestCountCategories:
    def test_totals_and_subcategory_map(self):
        df = pd.DataFrame(
            [
                {"raw_transaction": "a", "amount": "10.00", "category": "FOOD"},
                {"raw_transaction": "b", "amount": "5.00", "category": "FOOD RESTAURANTS"},
            ]
        )
        data = count_categories(df, {})
        assert data["FOOD"] == 15
        assert data["RESTAURANTS"] == 5
        # RESTAURANTS is recorded as a subcategory of FOOD.
        assert data["_map"]["RESTAURANTS"] == "FOOD"

    def test_ignored_categories_are_skipped(self):
        df = pd.DataFrame(
            [
                {"raw_transaction": "a", "amount": "10.00", "category": "FOOD"},
                {"raw_transaction": "b", "amount": "999.00", "category": "IGNORE"},
            ]
        )
        data = count_categories(df, {})
        assert data["FOOD"] == 10
        assert "IGNORE" not in data


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
