"""Unit tests for pure helper functions in analyze_pdf.py.

Heavy imports (LangChain, Docling, the per-bank extractors, dotenv) are mocked in
conftest.py, so importing analyze_pdf here only exercises pandas + the standard
library.
"""
import math

import pandas as pd
import pytest

from analyze_pdf import (
    date_column_index,
    description_column_index,
    amount_column_index,
    get_possible_column,
    invalid_float,
    is_valid_df,
    month_name_to_number,
    parse_money,
)


class TestMonthNameToNumber:
    def test_known_months(self):
        assert month_name_to_number("jan") == "01/"
        assert month_name_to_number("dec") == "12/"

    def test_case_insensitive_and_long_form(self):
        assert month_name_to_number("March") == "03/"

    def test_unknown_month_raises(self):
        with pytest.raises(ValueError):
            month_name_to_number("smarch")


class TestParseMoney:
    def test_dollar_sign_and_commas(self):
        assert parse_money("$1,234.56") == 1234.56

    def test_negative(self):
        assert parse_money("-45.00") == -45.0

    def test_non_numeric_is_nan(self):
        assert math.isnan(parse_money("not money"))

    def test_empty_is_nan(self):
        assert math.isnan(parse_money(""))


class TestInvalidFloat:
    def test_valid(self):
        assert invalid_float("12.5") is False

    def test_invalid(self):
        assert invalid_float("abc") is True


class TestIsValidDf:
    def test_all_present(self):
        assert is_valid_df([0, 1, 2]) is True

    def test_missing_column(self):
        assert is_valid_df([None, 1, 2]) is False

    def test_wrong_length(self):
        assert is_valid_df([0, 1]) is False


class TestColumnDetection:
    """Exact-name column matching (stable regardless of fuzzy-match behavior)."""

    def test_description_column(self):
        df = pd.DataFrame(columns=["Date Posted", "Description", "Amount"])
        assert description_column_index(df) == 1

    def test_date_column(self):
        df = pd.DataFrame(columns=["Date Posted", "Description", "Amount"])
        assert date_column_index(df) == 0

    def test_amount_column(self):
        df = pd.DataFrame(columns=["Date Posted", "Description", "Amount"])
        assert amount_column_index(df) == 2

    def test_get_possible_column_exact_match(self):
        df = pd.DataFrame(columns=["foo", "Description", "bar"])
        assert get_possible_column(df.columns, "Description") == 1
