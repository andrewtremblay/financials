import calendar
import math
import os
from datetime import timedelta
from pprint import pprint
import re
import urllib.request
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.documents import Document
from langchain_ollama import OllamaLLM
import pandas as pd
import categorize
import plaid_sync
from utils import load_pdf, export_to_csv, check_categorized_data, all_pdfs_in_folder, all_csvs_in_folder, load_pdf_as_dataframes, read_csv, count_categories, fmt_sankeymatic
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

_MONTH_ABBREV = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_RE = "January|February|March|April|May|June|July|August|September|October|November|December"

def extract_statement_year_month_from_pdf(pdf_path: str) -> tuple[int, int] | None:
    """
    Scan the raw text of a PDF for year-bearing dates and return (year, month)
    for the latest one found — typically the statement closing or due date.

    Recognised patterns (all anchored to 202x years):
      Numeric
        MM/DD/YYYY          01/23/2026
        YYYY-MM-DD          2026-01-23   (ISO 8601)
        MM-DD-YYYY          01-23-2026
      Named month (with day)
        Month D, YYYY       January 23, 2026
        Month D-DD, YYYY    January 1-30, 2026
        Month Dth, YYYY     June 3rd, 2025  (ordinals)
        Month D - Month D, YYYY   December 24 - January 23, 2026  (billing period)
        DD Month YYYY       23 January 2026
      Named month (no day)
        Month YYYY          January 2026
      Last resort
        YYYY alone          ©2026   → anchors year with month=12 (conservative)

    Returns None only if the text contains no 202x-era year at all.
    """
    try:
        docs = load_pdf(pdf_path)
    except Exception:
        return None
    text = " ".join(d.page_content for d in docs)

    found: list[tuple[int, int]] = []  # (year, month)

    def _mn(name: str) -> int | None:
        return _MONTH_ABBREV.get(name[:3].lower())

    def _add(year: str | int, month: str | int) -> None:
        try:
            y, m = int(year), int(month)
            if 2020 <= y <= 2099 and 1 <= m <= 12:
                found.append((y, m))
        except (ValueError, TypeError):
            pass

    # ── Numeric ───────────────────────────────────────────────────────────────
    for m in re.finditer(r'\b(\d{1,2})/\d{1,2}/(202\d)\b', text):
        _add(m.group(2), m.group(1))                                  # MM/DD/YYYY

    for m in re.finditer(r'\b(202\d)-(\d{2})-\d{2}\b', text):
        _add(m.group(1), m.group(2))                                  # YYYY-MM-DD

    for m in re.finditer(r'\b(\d{1,2})-\d{1,2}-(202\d)\b', text):
        _add(m.group(2), m.group(1))                                  # MM-DD-YYYY

    # ── Named month with day ──────────────────────────────────────────────────
    # "Month D, YYYY" / "Month D-DD, YYYY" (plain and range)
    for m in re.finditer(rf'({_MONTH_RE})\s+\d[\d\-]*,?\s+(202\d)', text, re.IGNORECASE):
        mn = _mn(m.group(1))
        if mn:
            _add(m.group(2), mn)

    # "Month Dth/st/nd/rd, YYYY" (ordinal day)
    for m in re.finditer(
        rf'({_MONTH_RE})\s+\d{{1,2}}(?:st|nd|rd|th),?\s+(202\d)', text, re.IGNORECASE
    ):
        mn = _mn(m.group(1))
        if mn:
            _add(m.group(2), mn)

    # "Month D - Month D, YYYY" (billing period; year applies to the closing month)
    for m in re.finditer(
        rf'(?:{_MONTH_RE})\s+\d+\s*[-–]\s*({_MONTH_RE})\s+\d+,?\s+(202\d)', text, re.IGNORECASE
    ):
        mn = _mn(m.group(1))
        if mn:
            _add(m.group(2), mn)

    # "DD Month YYYY"
    for m in re.finditer(rf'\b\d{{1,2}}\s+({_MONTH_RE})\s+(202\d)\b', text, re.IGNORECASE):
        mn = _mn(m.group(1))
        if mn:
            _add(m.group(2), mn)

    # ── Named month, no day ───────────────────────────────────────────────────
    # "Month YYYY" — catches "January 2026" style period labels
    for m in re.finditer(rf'\b({_MONTH_RE})\s+(202\d)\b', text, re.IGNORECASE):
        mn = _mn(m.group(1))
        if mn:
            _add(m.group(2), mn)

    if found:
        return max(found)

    # ── Last resort: standalone year ──────────────────────────────────────────
    # e.g. Barclays statements that only contain "©2026" with no month context.
    # month=12 is conservative: all transaction months (1–12) ≤ 12 → year attributed correctly.
    years = [int(m.group(1)) for m in re.finditer(r'\b(202\d)\b', text)]
    return (max(years), 12) if years else None


def csv_to_pdf_path(csv_path: str) -> str | None:
    """Return the source PDF path for a *_categorized.csv file, or None if not found."""
    base = csv_path.replace('_categorized.csv', '')
    for ext in ('.pdf', '.PDF'):
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def infer_year_month(date_str: str, stmt_year: int, stmt_month: int) -> str:
    """
    Given a MM/DD date string and a statement anchor (year, month), return 'YYYY-MM'.

    Dates whose month exceeds the anchor month belong to the prior year
    (e.g. a Feb-2026-anchored statement that includes Dec transactions → Dec 2025).
    Handles Docling artifacts like "01/03 01/03" by taking the first token.
    """
    clean = str(date_str).strip().split()[0]
    parts = clean.split('/')
    try:
        date_month = int(parts[0])
    except (ValueError, IndexError):
        return f"{stmt_year}-{stmt_month:02d}"
    year = stmt_year if date_month <= stmt_month else stmt_year - 1
    return f"{year}-{date_month:02d}"

def month_name_to_number(month: str) -> str:
    """Converts a month abbreviation (e.g. 'jan') to a date prefix (e.g. '01/')."""
    prefixes = {
        "jan": "01/", "feb": "02/", "mar": "03/", "apr": "04/",
        "may": "05/", "jun": "06/", "jul": "07/", "aug": "08/",
        "sep": "09/", "oct": "10/", "nov": "11/", "dec": "12/",
    }
    key = month.lower()[:3]
    if key not in prefixes:
        raise ValueError(f"Unknown month: {month!r}. Use a 3-letter abbreviation like 'jan', 'feb', etc.")
    return prefixes[key]


# Fast & brittle categorization using a regex process
def categorize_pdf_to_csv_v1(pdf_path: str, extract_documents: callable, categorize: callable, model: OllamaLLM) -> None:
    documents: list[Document] = load_pdf(pdf_path)
    transactions = extract_documents(documents)
    # print(f'Extracted {len(transactions)} transactions')
    categorized_data = categorize(model, transactions)
    check_categorized_data(categorized_data)
    output_csv = pdf_path.replace(".pdf", "_categorized.csv").replace(".PDF", "_categorized.csv")
    export_to_csv(categorized_data, output_csv)

# Slower but more accurate categorization using docling
def categorize_pdf_to_csv_v2(pdf_path: str, extract_dataframes: callable, categorize: callable, model: OllamaLLM) -> None:
    dataframes = load_pdf_as_dataframes(pdf_path)
    # print(f'Extracted {len(dataframes)} dataframes')
    transactions = extract_dataframes(dataframes, pdf_path)
    # print(f'Extracted {len(transactions)} transactions from dataframes')
    categorized_data = categorize(model, transactions)
    check_categorized_data(categorized_data)
    output_csv = pdf_path.replace(".pdf", "_categorized.csv").replace(".PDF", "_categorized.csv")
    export_to_csv(categorized_data, output_csv)


def get_possible_column(cols: pd.Index, colname: str) -> int | None:
    try:
        index = cols.get_loc(colname)
        if isinstance(index, int):
            return index
        # get_loc returned something other than a plain int (e.g. a slice or
        # boolean array for duplicate labels) -- fall through to fuzzy match below.
    except KeyError:
        pass
    # fall back to fuzzy match
    pattern = re.compile(colname)
    matching_cols = [col for col in cols if pattern.search(col)]
    if len(matching_cols) >= 1:
        index = cols.get_loc(matching_cols[0])
        if isinstance(index, int):
            return index
    return None

# Data-driven candidate lists, in priority order. Because get_possible_column
# now falls back to a regex search over the full column name, short distinctive
# substrings are enough to match verbose/nested column names produced by Docling
# (e.g. "Schwab Bank Investor Checking TM (continued).Activity (continued).Description").
DESCRIPTION_COLUMN_CANDIDATES = [
    "Description",
]

DATE_COLUMN_CANDIDATES = [
    "Date Posted",
    "Activity Posted",
    "Transaction Date",
]

AMOUNT_COLUMN_CANDIDATES = [
    "Debits",
    "Credits",
    "Amount",
]

def first_matching_column_index(cols: pd.Index, candidates: list[str]) -> int | None:
    for candidate in candidates:
        index = get_possible_column(cols, candidate)
        if index is not None:
            return index
    return None

def description_column_index(df: pd.DataFrame) -> int | None:
    return first_matching_column_index(df.columns, DESCRIPTION_COLUMN_CANDIDATES)


def date_column_index(df: pd.DataFrame) -> int | None:
    return first_matching_column_index(df.columns, DATE_COLUMN_CANDIDATES)


def amount_column_index(df: pd.DataFrame) -> int | None:
    return first_matching_column_index(df.columns, AMOUNT_COLUMN_CANDIDATES)

def columns_for_df(df) -> list[int]:
    date_idx = date_column_index(df)
    desc_idx = description_column_index(df)
    amount_idx = amount_column_index(df)
    return [date_idx, desc_idx, amount_idx]

def is_valid_df(cols: list[int]) -> bool: 
    return len(cols) == 3 and cols[0] is not None and cols[1] is not None and cols[2] is not None

def invalid_float(s):
    try:
        float(s)
        return False
    except ValueError:
        return True

def parse_money(s):
    # Remove $ and commas, keep negative sign if present
    cleaned = re.sub(r'[^\d.-]', '', s)
    if invalid_float(cleaned):
        return math.nan
    return float(cleaned)


def convert_dfs(df: pd.DataFrame, cols: list[int]) -> list[list[str]]:
    to_return = []
    credits_idx = get_possible_column(df.columns, "Credits")

    for index, row in df.iterrows():
        try:
            date = row.iloc[cols[0]]
            desc = row.iloc[cols[1]]
            orig_amt = row.iloc[cols[2]]
            if credits_idx is not None and row.iloc[credits_idx] is not None and row.iloc[credits_idx] != "":
                orig_amt = row.iloc[credits_idx]
            amt = math.nan
            # print(f'Extracted {date}:{desc}:{orig_amt}')
            if type(orig_amt) == str:
                amt = parse_money(orig_amt)
            if math.isnan(amt):
                # print(f"bad amt {orig_amt}")
                continue
            if date is None or date == "":
                # print(f"empty date: skipping")
                continue
            if desc is None or desc == "":
                # print(f"empty description: skipping")
                continue
            to_return.append([date, desc, amt])
        except IndexError:
            print(f"bad row {row}")
            continue
    return to_return

def _has_numeric_columns(df: pd.DataFrame) -> bool:
    return all(str(c).isdigit() for c in df.columns)


def extract_dataframes(dataframes: list[pd.DataFrame], origin: str) -> list[str]:
    # First pass: collect valid column indices keyed by column count so that
    # numeric-header continued pages (which may appear before or after a named
    # page) can borrow the right positional mapping.
    valid_cols_by_ncols: dict[int, list[int]] = {}
    for df in dataframes:
        cols = columns_for_df(df)
        if is_valid_df(cols):
            valid_cols_by_ncols[len(df.columns)] = cols

    valid_dataframes = []
    for df in dataframes:
        cols = columns_for_df(df)
        if is_valid_df(cols):
            rows = convert_dfs(df, cols)
            valid_dataframes.extend(rows)
        elif (
            _has_numeric_columns(df)
            and len(df.columns) in valid_cols_by_ncols
        ):
            # Continued page: Docling produced numeric headers — reuse column positions
            fallback = valid_cols_by_ncols[len(df.columns)]
            rows = convert_dfs(df, fallback)
            valid_dataframes.extend(rows)
        else:
            print(f'Skipping invalid dataframe in file:{origin} \n{", ".join(str(c) for c in df.columns)}\n')
    return valid_dataframes

def categorize_all_pdfs_in_folder(pdf_folder: str, pdf_to_csv: callable):
    print(f'\nReading folder {pdf_folder}\n')
    pdfs = all_pdfs_in_folder(pdf_folder)
    for pdf_file in pdfs:
        pdf_to_csv(pdf_file)

def _ollama_running() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False


def resolve_model():
    """
    Return the first available LLM, in priority order:
      1. Ollama gemma2:27b  (local, free — requires `ollama serve`)
      2. Claude claude-haiku-4-5  (fast, cheap — requires ANTHROPIC_API_KEY)
      3. OpenAI gpt-4o-mini  (requires OPENAI_API_KEY)

    Raises SystemExit with a clear message if nothing is available.
    """
    if _ollama_running():
        print("Using Ollama (gemma2:27b)")
        return OllamaLLM(model="gemma2:27b", temperature=0.0, request_timeout=60)

    if os.getenv("ANTHROPIC_API_KEY"):
        print("Using Anthropic (claude-haiku-4-5)")
        return ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0.0)

    if os.getenv("OPENAI_API_KEY"):
        print("Using OpenAI (gpt-4o-mini)")
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    raise SystemExit(
        "No LLM available. Start Ollama (`ollama serve`) or set ANTHROPIC_API_KEY / OPENAI_API_KEY in .env"
    )

INBOX_FOLDER = "data/inbox"
BANK_FOLDERS = ["data/boa_cc", "data/schwab", "data/barclays", "data/paypal"]
PLAID_FOLDER = "data/plaid"

SOURCES = ("plaid", "pdf", "all")


# Main function
def main(
    month: str | None = None,
    inbox_only: bool = False,
    source: str = "plaid",
    plaid_max_age_hours: float = 24.0,
):
    """
    source:
      "plaid" (default) — only data/plaid/ (Plaid API transactions), no PDF parsing.
      "pdf"              — only PDF parsing (data/inbox/ + bank folders), no Plaid.
      "all"              — both. No dedup between the two sources yet (TODO: future param).
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}. Use one of {SOURCES}.")

    model = resolve_model()
    csvs = []

    if source in ("pdf", "all"):
        # Process inbox in-place (v2 is bank-agnostic — no routing/copying needed)
        categorize_all_pdfs_in_folder(INBOX_FOLDER, lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))
        csvs.extend(all_csvs_in_folder(INBOX_FOLDER))

        if not inbox_only:
            # Also process any PDFs already in bank-specific subfolders (legacy files not in inbox)
            for folder in BANK_FOLDERS:
                categorize_all_pdfs_in_folder(folder, lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))
                csvs.extend(all_csvs_in_folder(folder))

    if source in ("plaid", "all"):
        # Sync (skipping items synced within plaid_max_age_hours) then read whatever's in data/plaid/.
        plaid_sync.sync_all_items(model, max_age=timedelta(hours=plaid_max_age_hours))
        csvs.extend(all_csvs_in_folder(PLAID_FOLDER))

    rollup_csv = []
    data_total = {}
    data_by_month: dict[str, dict] = {}

    for csv_file_path in csvs:
        csv_data_df = read_csv(csv_file_path)
        if csv_data_df.empty:
            continue

        # Annotate each row with its inferred calendar year-month.
        # Plaid CSVs (data/plaid/) already carry an exact year_month column,
        # stamped from Plaid's own ISO transaction dates — no PDF to infer from.
        if 'year_month' in csv_data_df.columns:
            pass
        else:
            pdf_path = csv_to_pdf_path(csv_file_path)
            stmt_date = extract_statement_year_month_from_pdf(pdf_path) if pdf_path else None
            if stmt_date and 'date' in csv_data_df.columns:
                stmt_year, stmt_month = stmt_date
                csv_data_df = csv_data_df.copy()
                csv_data_df['year_month'] = csv_data_df['date'].astype(str).apply(
                    lambda d: infer_year_month(d, stmt_year, stmt_month)
                )
            else:
                csv_data_df['year_month'] = 'unknown'

        records = csv_data_df.to_dict('records')
        for record in records:
            record['source'] = csv_file_path
        rollup_csv.extend(records)

        data_total = count_categories(csv_data_df, data_total)
        for ym, group in csv_data_df.groupby('year_month'):
            if ym not in data_by_month:
                data_by_month[ym] = {}
            data_by_month[ym] = count_categories(group, data_by_month[ym])

    export_to_csv(rollup_csv, "rollup.csv")
    print(f"Wrote {len(rollup_csv)} transactions to rollup.csv\n")

    # ── Monthly reports ──────────────────────────────────────────────────────
    month_filter = month_name_to_number(month).rstrip('/') if month else None
    requested_sankey = None

    for ym in sorted(data_by_month.keys()):
        year_str, mon_str = ym.split('-')
        label = f"{calendar.month_name[int(mon_str)]} {year_str}"
        print(f"\n{'='*52}")
        print(f"  {label}")
        print(f"{'='*52}\n")
        sankey = fmt_sankeymatic(data_by_month[ym])
        print(sankey)
        if month_filter and mon_str == month_filter:
            requested_sankey = sankey

    # ── Total ────────────────────────────────────────────────────────────────
    print(f"\n{'='*52}")
    print(f"  TOTAL  ({', '.join(sorted(data_by_month.keys()))})")
    print(f"{'='*52}\n")
    total_sankey = fmt_sankeymatic(data_total)
    print(total_sankey)

    return requested_sankey if requested_sankey else total_sankey

