"""
Tests for analyze_pdf.py helper functions.

Run with: uv run pytest test_analyze_pdf.py -v
"""
import math
import sys
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Patch heavy dependencies before importing anything
for mod in [
    "langchain_openai",
    "langchain_ollama",
    "langchain_anthropic",
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "docling",
    "docling.document_converter",
    "memo",
    "dotenv",
    "categorize",
]:
    sys.modules[mod] = MagicMock()

# Prevent models dict from instantiating real LLM clients at import time
sys.modules["langchain_openai"].ChatOpenAI = MagicMock(return_value=MagicMock())
sys.modules["langchain_ollama"].OllamaLLM = MagicMock(return_value=MagicMock())
sys.modules["langchain_anthropic"].ChatAnthropic = MagicMock(return_value=MagicMock())

import analyze_pdf  # noqa: E402 — used directly for source-routing tests below
from analyze_pdf import (  # noqa: E402
    month_name_to_number,
    parse_money,
    invalid_float,
    get_possible_column,
    is_valid_df,
    description_column_index,
    date_column_index,
    amount_column_index,
    extract_dataframes,
    convert_dfs,
    extract_statement_year_month_from_pdf,
    csv_to_pdf_path,
    infer_year_month,
)


# ---------------------------------------------------------------------------
# month_name_to_number
# ---------------------------------------------------------------------------

class TestMonthNameToNumber:
    @pytest.mark.parametrize("month,expected", [
        ("jan", "01/"), ("feb", "02/"), ("mar", "03/"), ("apr", "04/"),
        ("may", "05/"), ("jun", "06/"), ("jul", "07/"), ("aug", "08/"),
        ("sep", "09/"), ("oct", "10/"), ("nov", "11/"), ("dec", "12/"),
    ])
    def test_lowercase(self, month, expected):
        assert month_name_to_number(month) == expected

    def test_uppercase(self):
        assert month_name_to_number("JAN") == "01/"

    def test_mixed_case(self):
        assert month_name_to_number("Feb") == "02/"

    def test_full_month_name_truncated(self):
        # Only first 3 chars are used
        assert month_name_to_number("january") == "01/"
        assert month_name_to_number("december") == "12/"

    def test_unknown_month_raises(self):
        with pytest.raises(ValueError, match="Unknown month"):
            month_name_to_number("xyz")


# ---------------------------------------------------------------------------
# parse_money / invalid_float
# ---------------------------------------------------------------------------

class TestInvalidFloat:
    def test_valid_integer_string(self):
        assert invalid_float("123") is False

    def test_valid_decimal_string(self):
        assert invalid_float("45.67") is False

    def test_negative_string(self):
        assert invalid_float("-10.5") is False

    def test_non_numeric_string(self):
        assert invalid_float("abc") is True

    def test_empty_string(self):
        assert invalid_float("") is True


class TestParseMoney:
    def test_plain_integer(self):
        assert parse_money("100") == 100.0

    def test_decimal(self):
        assert parse_money("45.67") == 45.67

    def test_dollar_sign_stripped(self):
        assert parse_money("$1,234.56") == 1234.56

    def test_negative_preserved(self):
        assert parse_money("-50.00") == -50.0

    def test_negative_with_dollar(self):
        assert parse_money("-$75.00") == -75.0

    def test_comma_stripped(self):
        assert parse_money("1,000.00") == 1000.0

    def test_unparseable_returns_nan(self):
        result = parse_money("N/A")
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# get_possible_column
# ---------------------------------------------------------------------------

class TestGetPossibleColumn:
    def _cols(self, names):
        return pd.Index(names)

    def test_exact_match(self):
        cols = self._cols(["Date Posted", "Description", "Amount"])
        assert get_possible_column(cols, "Description") == 1

    def test_no_match_returns_none(self):
        cols = self._cols(["Date Posted", "Description", "Amount"])
        assert get_possible_column(cols, "Balance") is None

    def test_partial_name_fuzzy_matches(self):
        # get_possible_column falls back to a regex search over the full
        # column name, so a short distinctive substring matches verbose/
        # nested column names produced by Docling.
        cols = self._cols(["Activity.Date Posted", "Activity.Description", "Activity.Amount"])
        result = get_possible_column(cols, "Description")
        assert result == 1

    def test_exact_substring_fuzzy_matches(self):
        cols = self._cols(["Foo Description", "Bar Description", "Amount"])
        result = get_possible_column(cols, "Description")
        assert result == 0


# ---------------------------------------------------------------------------
# Column-detection helpers
# ---------------------------------------------------------------------------

class TestColumnDetection:
    def _df(self, col_names):
        return pd.DataFrame(columns=col_names)

    def test_description_column_standard(self):
        df = self._df(["Date Posted", "Description", "Amount"])
        assert description_column_index(df) == 1

    def test_date_column_standard(self):
        df = self._df(["Date Posted", "Description", "Amount"])
        assert date_column_index(df) == 0

    def test_amount_column_standard(self):
        df = self._df(["Date Posted", "Description", "Amount"])
        assert amount_column_index(df) == 2

    def test_transaction_date_fallback(self):
        df = self._df(["Transaction Date", "Description", "Amount"])
        assert date_column_index(df) == 0

    def test_debits_amount_column(self):
        df = self._df(["Date Posted", "Description", "Debits"])
        assert amount_column_index(df) == 2

    def test_credits_amount_column(self):
        df = self._df(["Date Posted", "Description", "Credits"])
        assert amount_column_index(df) == 2

    def test_missing_description_returns_none(self):
        df = self._df(["Date Posted", "Amount"])
        assert description_column_index(df) is None

    def test_missing_date_returns_none(self):
        df = self._df(["Description", "Amount"])
        assert date_column_index(df) is None


# ---------------------------------------------------------------------------
# is_valid_df
# ---------------------------------------------------------------------------

class TestIsValidDf:
    def test_all_present(self):
        assert is_valid_df([0, 1, 2]) is True

    def test_date_missing(self):
        assert is_valid_df([None, 1, 2]) is False

    def test_description_missing(self):
        assert is_valid_df([0, None, 2]) is False

    def test_amount_missing(self):
        assert is_valid_df([0, 1, None]) is False

    def test_all_missing(self):
        assert is_valid_df([None, None, None]) is False

    def test_wrong_length(self):
        assert is_valid_df([0, 1]) is False


# ---------------------------------------------------------------------------
# convert_dfs / extract_dataframes
# ---------------------------------------------------------------------------

class TestConvertDfs:
    def _make_df(self, rows, columns=None):
        cols = columns or ["Date Posted", "Description", "Amount"]
        return pd.DataFrame(rows, columns=cols)

    def test_basic_row_extraction(self):
        df = self._make_df([["01/15", "STARBUCKS", "4.50"]])
        result = convert_dfs(df, [0, 1, 2])
        assert len(result) == 1
        assert result[0][0] == "01/15"
        assert result[0][1] == "STARBUCKS"
        assert result[0][2] == 4.50

    def test_non_numeric_amount_skipped(self):
        df = self._make_df([["01/15", "STARBUCKS", "N/A"]])
        result = convert_dfs(df, [0, 1, 2])
        assert result == []

    def test_empty_date_skipped(self):
        df = self._make_df([["", "STARBUCKS", "4.50"]])
        result = convert_dfs(df, [0, 1, 2])
        assert result == []

    def test_empty_description_skipped(self):
        df = self._make_df([["01/15", "", "4.50"]])
        result = convert_dfs(df, [0, 1, 2])
        assert result == []

    def test_multiple_valid_rows(self):
        df = self._make_df([
            ["01/15", "STARBUCKS", "4.50"],
            ["01/16", "SHELL OIL", "35.00"],
        ])
        result = convert_dfs(df, [0, 1, 2])
        assert len(result) == 2

    def test_mixed_valid_invalid_rows(self):
        df = self._make_df([
            ["01/15", "STARBUCKS", "4.50"],
            ["01/16", "", "35.00"],    # empty description → skip
            ["01/17", "AMAZON", "N/A"],  # bad amount → skip
        ])
        result = convert_dfs(df, [0, 1, 2])
        assert len(result) == 1
        assert result[0][1] == "STARBUCKS"


class TestExtractDataframes:
    def _make_df(self, rows, columns=None):
        cols = columns or ["Date Posted", "Description", "Amount"]
        return pd.DataFrame(rows, columns=cols)

    def test_valid_dataframe_extracted(self):
        df = self._make_df([["01/15", "STARBUCKS", "4.50"]])
        result = extract_dataframes([df], "test.pdf")
        assert len(result) == 1

    def test_invalid_columns_skipped(self):
        df = self._make_df([["foo", "bar", "baz"]], columns=["X", "Y", "Z"])
        result = extract_dataframes([df], "test.pdf")
        assert result == []

    def test_multiple_dfs_combined(self):
        df1 = self._make_df([["01/15", "STARBUCKS", "4.50"]])
        df2 = self._make_df([["01/16", "AMAZON", "25.00"]])
        result = extract_dataframes([df1, df2], "test.pdf")
        assert len(result) == 2

    def test_empty_list_returns_empty(self):
        assert extract_dataframes([], "test.pdf") == []


# ---------------------------------------------------------------------------
# extract_statement_year_month_from_pdf
# ---------------------------------------------------------------------------

class TestExtractStatementYearMonth:
    def _make_docs(self, text):
        doc = MagicMock()
        doc.page_content = text
        return [doc]

    def _patch_load(self, text):
        return patch("analyze_pdf.load_pdf", return_value=self._make_docs(text))

    def test_mdy_format(self):
        with self._patch_load("Payment due 02/20/2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 2)

    def test_month_name_period_format(self):
        with self._patch_load("Statement period: January 1-30, 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_month_name_with_day_and_year(self):
        with self._patch_load("Closing date January 23, 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_returns_latest_date_as_anchor(self):
        # Statement spans Dec 2025 – Jan 2026; anchor should be the latest
        with self._patch_load("12/15/2025 transaction ... 01/10/2026 closing"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_multiple_mdy_returns_max(self):
        with self._patch_load("01/05/2026 ... 02/20/2026 ... 01/15/2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 2)

    def test_no_year_dates_returns_none(self):
        with self._patch_load("transaction on 01/15 for $4.50"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result is None

    def test_load_failure_returns_none(self):
        with patch("analyze_pdf.load_pdf", side_effect=Exception("file not found")):
            result = extract_statement_year_month_from_pdf("missing.pdf")
        assert result is None

    def test_schwab_period_line(self):
        with self._patch_load("Interest Earned 01/01/2026 to 01/30/2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_dec_statement_with_nov_period(self):
        # Dec 2025 statement with explicit day in period line (as seen in real Schwab PDFs)
        with self._patch_load("November 1-30, 2025 ... December 31, 2025 ending balance"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2025, 12)

    # ── New patterns ──────────────────────────────────────────────────────────

    def test_iso_8601_format(self):
        with self._patch_load("transaction on 2026-01-15"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_hyphen_separated_mdy(self):
        with self._patch_load("payment due 02-20-2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 2)

    def test_ordinal_st(self):
        with self._patch_load("statement closing January 1st, 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_ordinal_nd(self):
        with self._patch_load("February 2nd, 2026 due date"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 2)

    def test_ordinal_rd(self):
        with self._patch_load("June 3rd, 2025"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2025, 6)

    def test_ordinal_th(self):
        with self._patch_load("closed on November 30th, 2025"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2025, 11)

    def test_billing_period_month_range(self):
        # BOA style: "December 24 - January 23, 2026" — anchor is the closing month
        with self._patch_load("December 24 - January 23, 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_billing_period_same_month(self):
        with self._patch_load("January 1 - January 31, 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_dd_month_yyyy(self):
        with self._patch_load("issued 23 January 2026"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_month_yyyy_no_day(self):
        # Schwab period headers like "January 2026"
        with self._patch_load("January 2026 statement period"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 1)

    def test_month_yyyy_later_month_wins(self):
        # Marketing text with a future month shouldn't break year inference
        with self._patch_load("February 2026 closing date ... August 2026 program change"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 8)  # max wins; year is still correct for Feb transactions

    def test_standalone_year_fallback(self):
        # Barclays style: only "©2026" in the whole document
        with self._patch_load("©2026 Barclays Bank Delaware, Member FDIC. Total fees in 2026."):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 12)  # conservative month=12 so all months → 2026

    def test_standalone_year_no_match_returns_none(self):
        with self._patch_load("no dates or years here at all"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result is None

    def test_iso_beats_mdy_when_later(self):
        # ISO date in March vs MM/DD/YYYY in January — March wins
        with self._patch_load("paid 01/15/2026 ... issued 2026-03-01"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2026, 3)

    def test_cross_year_billing_period(self):
        # "November 5 - December 5, 2025" — closing month December 2025
        with self._patch_load("November 5 - December 5, 2025 statement period"):
            result = extract_statement_year_month_from_pdf("dummy.pdf")
        assert result == (2025, 12)


# ---------------------------------------------------------------------------
# csv_to_pdf_path
# ---------------------------------------------------------------------------

class TestCsvToPdfPath:
    def test_finds_lowercase_pdf(self, tmp_path):
        pdf = tmp_path / "BOA_stmt.pdf"
        pdf.touch()
        csv = str(tmp_path / "BOA_stmt_categorized.csv")
        assert csv_to_pdf_path(csv) == str(pdf)

    def test_finds_uppercase_PDF(self, tmp_path):
        # On case-insensitive filesystems (macOS) .PDF and .pdf are the same file,
        # so just verify the path resolves to something that exists.
        pdf = tmp_path / "Schwab_stmt.PDF"
        pdf.touch()
        csv = str(tmp_path / "Schwab_stmt_categorized.csv")
        result = csv_to_pdf_path(csv)
        assert result is not None
        assert result.lower().endswith(".pdf")

    def test_returns_none_when_pdf_missing(self, tmp_path):
        csv = str(tmp_path / "missing_categorized.csv")
        assert csv_to_pdf_path(csv) is None


# ---------------------------------------------------------------------------
# infer_year_month
# ---------------------------------------------------------------------------

class TestInferYearMonth:
    def test_same_month_as_anchor(self):
        assert infer_year_month("01/15", 2026, 1) == "2026-01"

    def test_month_before_anchor(self):
        # Dec transaction in a Feb-2026-anchored statement → Dec 2025
        assert infer_year_month("12/31", 2026, 2) == "2025-12"

    def test_month_equal_to_anchor(self):
        assert infer_year_month("02/05", 2026, 2) == "2026-02"

    def test_docling_artifact_duplicate_date(self):
        # "01/03 01/03" artifact — only first token used
        assert infer_year_month("01/03 01/03", 2026, 1) == "2026-01"

    def test_december_anchor_all_same_year(self):
        assert infer_year_month("11/15", 2025, 12) == "2025-11"
        assert infer_year_month("12/31", 2025, 12) == "2025-12"

    def test_unparseable_date_falls_back_to_anchor(self):
        assert infer_year_month("bad", 2026, 3) == "2026-03"


# ---------------------------------------------------------------------------
# main() source routing — mocks every side-effecting call (LLM, disk, network)
# ---------------------------------------------------------------------------

class TestMainSourceRouting:
    def _run(self, source, inbox_only=False):
        with patch("analyze_pdf.resolve_model", return_value=MagicMock()), \
             patch("analyze_pdf.plaid_sync.sync_all_items") as mock_sync, \
             patch("analyze_pdf.categorize_all_pdfs_in_folder") as mock_pdf_folder, \
             patch("analyze_pdf.all_csvs_in_folder", return_value=[]), \
             patch("analyze_pdf.export_to_csv") as mock_export:
            analyze_pdf.main(source=source, inbox_only=inbox_only)
            return mock_sync, mock_pdf_folder, mock_export

    def test_plaid_source_skips_pdf_processing(self):
        mock_sync, mock_pdf_folder, mock_export = self._run("plaid")
        assert mock_sync.called
        assert not mock_pdf_folder.called

    def test_pdf_source_skips_plaid_sync(self):
        mock_sync, mock_pdf_folder, mock_export = self._run("pdf")
        assert not mock_sync.called
        assert mock_pdf_folder.called

    def test_all_source_runs_both(self):
        mock_sync, mock_pdf_folder, mock_export = self._run("all")
        assert mock_sync.called
        assert mock_pdf_folder.called

    def test_pdf_source_respects_inbox_only(self):
        # inbox_only=True should process INBOX_FOLDER but skip BANK_FOLDERS —
        # categorize_all_pdfs_in_folder should be called exactly once (inbox only).
        mock_sync, mock_pdf_folder, mock_export = self._run("pdf", inbox_only=True)
        assert mock_pdf_folder.call_count == 1

    def test_pdf_source_without_inbox_only_processes_bank_folders_too(self):
        mock_sync, mock_pdf_folder, mock_export = self._run("pdf", inbox_only=False)
        # inbox + 4 bank folders
        assert mock_pdf_folder.call_count == 1 + len(analyze_pdf.BANK_FOLDERS)

    def test_unknown_source_raises(self):
        with patch("analyze_pdf.resolve_model", return_value=MagicMock()):
            with pytest.raises(ValueError, match="Unknown source"):
                analyze_pdf.main(source="bogus")

    def test_plaid_max_age_hours_passed_through(self):
        with patch("analyze_pdf.resolve_model", return_value=MagicMock()), \
             patch("analyze_pdf.plaid_sync.sync_all_items") as mock_sync, \
             patch("analyze_pdf.all_csvs_in_folder", return_value=[]), \
             patch("analyze_pdf.export_to_csv"):
            analyze_pdf.main(source="plaid", plaid_max_age_hours=6.0)
            _, kwargs = mock_sync.call_args
            assert kwargs["max_age"] == timedelta(hours=6.0)
