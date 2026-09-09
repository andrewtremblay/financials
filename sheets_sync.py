"""
sheets_sync.py — add one monthly tab per missing month to the household
budget Google Sheet, populating the ACTUAL columns from data/plaid/*.csv.

The sheet already has hand-built tabs (September 2025 -> March 2026) with a
fixed layout: column B holds income/savings line items, column H holds
expense line items, and each has PROJECTED/ACTUAL/DIFFERENCE sub-columns.
New tabs are created by duplicating the most recent existing tab (carrying
its PROJECTED values forward as a starting budget) and overwriting just the
ACTUAL cells with amounts aggregated from Plaid data, mapped via
sheet_category_map.CATEGORY_TO_LINE_ITEM.

Categories with no confident line-item mapping (sheet_category_map.
NEEDS_REVIEW_CATEGORIES, e.g. INSURANCE — which legitimately splits across
four different insurance lines) are never guessed into a cell; they're
totaled per month and reported so nothing is silently misallocated.

Usage:
    uv run sheets_sync.py --dry-run          # preview, no credentials needed
    uv run sheets_sync.py                    # write to the sheet
    uv run sheets_sync.py --months 2026-04 2026-05
"""

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

import budget_aggregate
import budget_schema

SPREADSHEET_ID = "1oCSgGmsuizUfhpp-74RJrDP3OBlmkPWY682CloOf42E"
CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")

# Row layout is defined once in budget_schema.py (the single source of truth
# shared with the API); these are derived views of it for the sheet-cell
# representation this script works with.
INCOME_SAVINGS_ROWS = budget_schema.income_savings_rows()
INCOME_SAVINGS_COLUMN = "D"

EXPENSE_ROWS = budget_schema.expense_rows()
# "Other" appears once per expense section at a different row each time.
EXPENSE_OTHER_ROWS = budget_schema.expense_other_rows()
EXPENSE_COLUMN = "J"

TEMPLATE_TAB = "March 2026"  # most recent existing tab; new tabs are duplicated from this one

# Line items with no reliable Plaid signal — never computed from Plaid; the
# ACTUAL cell just mirrors whatever the PROJECTED cell says each sync.
# {(actual_col, actual_row): projected_col}. Emergency Fund, Retirement
# IRA/Roth/MTRS, 401k+Match, Home Projects/Apt. Rent — employer
# withholding/transfers that never touch a linked account; Cleaning Service —
# paid via Venmo, not identifiable from a Plaid category (2026-07-29,
# user-specified).
COPY_PROJECTED_CELLS = budget_schema.copy_projected_cells()
STATIC_CELLS = set(COPY_PROJECTED_CELLS)

# Line items with no reliable Plaid signal (the "690 Adams St" deposits
# initially assumed to be Apartment Rental Income turned out to be credit
# card payments — 2026-07-29) but a known real value — forced to this exact
# figure on every sync, both PROJECTED and ACTUAL, regardless of Plaid data.
FIXED_CELLS = budget_schema.fixed_cells()


# Short forms for note breakdowns (2026-07-29, user-specified: "BofA card
# 0081" not "Bank of America credit card 0081").
INSTITUTION_ABBREVIATIONS = {
    "Bank of America": "BofA",
    "Charles Schwab": "Schwab",
    "Barclays - Cards": "Barclays",
}
SUBTYPE_ABBREVIATIONS = {"credit card": "card"}


def _account_labels() -> dict[str, str]:
    """account_id -> short account label (e.g. 'BofA card 0081'), for tagging
    note breakdowns with the source of each transaction."""
    with open("plaid_items.json") as f:
        items = json.load(f)
    labels = {}
    for item in items.values():
        institution = INSTITUTION_ABBREVIATIONS.get(item["institution_name"], item["institution_name"])
        for account in item["accounts"]:
            subtype = SUBTYPE_ABBREVIATIONS.get(account["subtype"], account["subtype"])
            labels[account["account_id"]] = f"{institution} {subtype} {account['mask']}"
    return labels


def load_all_transactions() -> pd.DataFrame:
    account_labels = _account_labels()
    frames = []
    for path in glob.glob("data/plaid/*_categorized.csv"):
        account_id = Path(path).stem.removesuffix("_categorized")
        df = pd.read_csv(path)
        df["account"] = account_labels.get(account_id, account_id)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _line_item_cell(section: str, line_item: str) -> tuple[str, int] | None:
    """None means this (section, line_item) has no physical row on the
    Sheet at all — always a custom category created through the dashboard's
    "add a new category" flow (see custom_categories.py) after this Sheet's
    fixed row layout was set. Unlike the web API's aggregate_month_json,
    which can synthesize a new JSON entry for these, a real Sheet tab has no
    such thing as a synthetic row — callers must route the money to
    needs_review instead of writing it (2026-09-08 fix; found live: "James
    Education Fund" crashed this whole sync with a bare KeyError)."""
    if section in ("income", "savings"):
        row = INCOME_SAVINGS_ROWS.get(line_item)
        return (INCOME_SAVINGS_COLUMN, row) if row is not None else None
    row_num = EXPENSE_OTHER_ROWS.get(section) if line_item == "Other" else EXPENSE_ROWS.get(line_item)
    return (EXPENSE_COLUMN, row_num) if row_num is not None else None


def aggregate_month(df: pd.DataFrame, year_month: str) -> tuple[dict, dict, dict]:
    """
    Returns (cell_values, cell_notes, needs_review) for one year_month ("YYYY-MM"):
    - cell_values: {(column_letter, row): amount} ready to write
    - cell_notes: {(column_letter, row): breakdown text} — the transactions
      behind each amount, so the sheet's note matches what's actually there
    - needs_review: {category: (amount, count)} excluded from the sheet

    Thin adapter over budget_aggregate._resolve_month, which holds the actual
    category-resolution rules (UTILITIES splitting, NEEDS_REVIEW routing,
    hierarchical fallback, Zus/brokerage netting) shared with the web API.
    """
    totals, txns, needs_review_txns = budget_aggregate._resolve_month(df, year_month)

    cell_values: dict[tuple[str, int], float] = {}
    cell_notes: dict[tuple[str, int], str] = {}
    needs_review: dict[str, tuple[float, int]] = {
        category: (sum(t["amount"] for t in items), len(items))
        for category, items in needs_review_txns.items()
    }
    for (section, line_item), total in totals.items():
        cell = _line_item_cell(section, line_item)
        if cell is None:
            # Custom category with no physical Sheet row -- flag it instead
            # of silently dropping the money or crashing the sync.
            items = txns[(section, line_item)]
            needs_review[f"{section} / {line_item} (custom category, no Sheet row)"] = (
                sum(t["amount"] for t in items), len(items),
            )
            continue
        if cell in STATIC_CELLS or cell in FIXED_CELLS:
            continue
        cell_values[cell] = round(total, 2)
        cell_notes[cell] = budget_aggregate.format_cell_note(txns[(section, line_item)])

    return cell_values, cell_notes, needs_review


def missing_actual_rows(cell_values: dict) -> list[str]:
    """Line items with no Plaid data this month — their stale ACTUAL value
    (copied from the template tab) must be zeroed, not left in place. Static
    cells (401k, apartment rent — untracked accounts) are left untouched."""
    written_income_savings_rows = {r for (c, r) in cell_values if c == INCOME_SAVINGS_COLUMN}
    written_expense_rows = {r for (c, r) in cell_values if c == EXPENSE_COLUMN}
    missing = []
    for line_item, row_num in INCOME_SAVINGS_ROWS.items():
        cell = (INCOME_SAVINGS_COLUMN, row_num)
        if row_num not in written_income_savings_rows and cell not in STATIC_CELLS and cell not in FIXED_CELLS:
            missing.append((INCOME_SAVINGS_COLUMN, row_num, line_item))
    for line_item, row_num in EXPENSE_ROWS.items():
        cell = (EXPENSE_COLUMN, row_num)
        if row_num not in written_expense_rows and cell not in STATIC_CELLS and cell not in FIXED_CELLS:
            missing.append((EXPENSE_COLUMN, row_num, line_item))
    for section, row_num in EXPENSE_OTHER_ROWS.items():
        cell = (EXPENSE_COLUMN, row_num)
        if row_num not in written_expense_rows and cell not in STATIC_CELLS and cell not in FIXED_CELLS:
            missing.append((EXPENSE_COLUMN, row_num, f"{section} Other"))
    return missing


def month_tab_name(year_month: str) -> str:
    dt = datetime.strptime(year_month, "%Y-%m")
    return dt.strftime("%B %Y")


def year_tab_name(year_months: list[str]) -> str:
    start = datetime.strptime(year_months[0], "%Y-%m")
    end = datetime.strptime(year_months[-1], "%Y-%m")
    return f"Yearly ({start.strftime('%b %Y')} - {end.strftime('%b %Y')})"


def _all_line_item_cells(sections: tuple = budget_schema.BUDGET_SECTIONS) -> list[tuple[str, str, int, str]]:
    """[(label, actual_col, row, proj_col)] for every physical line-item row
    on a month tab, including each section's "Other" catch-all row."""
    cells = []
    for s in sections:
        for li in s.line_items:
            cells.append((li.label, s.actual_column, li.row, s.projected_column))
        if s.other_row is not None:
            cells.append(("Other", s.actual_column, s.other_row, s.projected_column))
    return cells


def _sum_formula(col: str, row: int, month_tabs: list[str]) -> str:
    """A live SUM formula referencing this cell on each month tab (sheet
    names with spaces need single-quoting in A1 notation)."""
    refs = ",".join(f"'{tab}'!{col}{row}" for tab in month_tabs)
    return f"=SUM({refs})"


def year_formulas(gc_spreadsheet, year_months: list[str]) -> tuple[dict[tuple[str, int], str], list[str]]:
    """Builds live SUM-formula strings referencing each month's own tab cell,
    rather than computing totals in Python -- so the yearly tab keeps
    tracking a month tab if it's edited later (a manual correction, a
    re-sync), instead of going stale like a one-time computed value would.

    Returns ({(col, row): formula}, missing_tabs); missing_tabs lists any
    year_months with no existing tab (excluded from the formula entirely,
    rather than referencing a nonexistent sheet and producing #REF!).
    """
    existing_tabs = {ws.title for ws in gc_spreadsheet.worksheets()}
    month_tabs = [month_tab_name(ym) for ym in year_months]
    missing_tabs = [t for t in month_tabs if t not in existing_tabs]
    present_tabs = [t for t in month_tabs if t in existing_tabs]

    formulas: dict[tuple[str, int], str] = {}
    for _, actual_col, row, proj_col in _all_line_item_cells():
        formulas[(proj_col, row)] = _sum_formula(proj_col, row, present_tabs)
        formulas[(actual_col, row)] = _sum_formula(actual_col, row, present_tabs)
    return formulas, missing_tabs


def sync_year(gc_spreadsheet, tab_name: str, year_months: list[str], dry_run: bool):
    if dry_run:
        print(f"  Would create tab '{tab_name}' (duplicated from '{TEMPLATE_TAB}'), "
              f"with SUM formulas across {len(year_months)} months: {year_months[0]}..{year_months[-1]}")
        return

    formulas, missing_tabs = year_formulas(gc_spreadsheet, year_months)
    if missing_tabs:
        print(f"  WARNING: no tab found for {missing_tabs} -- excluded from the SUM formulas")

    existing = [ws.title for ws in gc_spreadsheet.worksheets()]
    if tab_name in existing:
        ws = gc_spreadsheet.worksheet(tab_name)
        action = "Updated"
    else:
        template = gc_spreadsheet.worksheet(TEMPLATE_TAB)
        ws = template.duplicate(insert_sheet_index=0, new_sheet_name=tab_name)
        action = "Created"

    ws.update_acell("B1", tab_name)

    note = (f"Yearly total across {len(year_months) - len(missing_tabs)} months "
            f"({year_months[0]} to {year_months[-1]}) -- live SUM formula referencing each month's own tab.")
    updates = [{"range": f"{col}{row}", "values": [[formula]]} for (col, row), formula in formulas.items()]
    notes_to_set = {f"{col}{row}": note for (col, row) in formulas}
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    ws.update_notes(notes_to_set)

    print(f"  {action} '{tab_name}': wrote {len(formulas)} live SUM formulas across {len(year_months)} months")


def sync_month(gc_spreadsheet, year_month: str, cell_values: dict, cell_notes: dict, dry_run: bool):
    tab_name = month_tab_name(year_month)

    if dry_run:
        print(f"  Would create tab '{tab_name}' (duplicated from '{TEMPLATE_TAB}')")
        return

    existing = [ws.title for ws in gc_spreadsheet.worksheets()]
    if tab_name in existing:
        ws = gc_spreadsheet.worksheet(tab_name)
        action = "Updated"
    else:
        template = gc_spreadsheet.worksheet(TEMPLATE_TAB)
        ws = template.duplicate(insert_sheet_index=0, new_sheet_name=tab_name)
        dt = datetime.strptime(year_month, "%Y-%m")
        ws.update_acell("B1", dt.strftime("%m/%d/%Y"))
        action = "Created"

    missing = missing_actual_rows(cell_values)
    updates = [{"range": f"{col}{row}", "values": [[0]]} for col, row, _ in missing]
    updates += [{"range": f"{col}{row}", "values": [[amount]]} for (col, row), amount in cell_values.items()]
    updates += [{"range": f"{col}{row}", "values": [[amount]]} for (col, row), amount in FIXED_CELLS.items()]
    ws.batch_update(updates, value_input_option="USER_ENTERED")

    # Cells with no reliable Plaid signal: ACTUAL just mirrors whatever
    # PROJECTED says, read live so editing the projected value propagates.
    static_items = list(COPY_PROJECTED_CELLS.items())
    projected_cells = [f"{proj_col}{row}" for (_, row), proj_col in static_items]
    projected_values = ws.batch_get(projected_cells, value_render_option="UNFORMATTED_VALUE")
    copy_updates = [
        {"range": f"{col}{row}", "values": [[(vals[0][0] if vals and vals[0] else 0)]]}
        for ((col, row), _), vals in zip(static_items, projected_values)
    ]
    ws.batch_update(copy_updates, value_input_option="USER_ENTERED")

    # The template's ACTUAL-column notes are stale per-transaction breakdowns
    # from whatever month it was copied from — replace them with this month's
    # real breakdown, or clear them where there's nothing to show (2026-07-29).
    notes_to_set = {f"{col}{row}": text for (col, row), text in cell_notes.items() if text}
    for (col, row) in FIXED_CELLS:
        notes_to_set[f"{col}{row}"] = "Fixed estimate — no reliable Plaid signal for apartment rental income (2026-07-29)."
    for (col, row), proj_col in COPY_PROJECTED_CELLS.items():
        notes_to_set[f"{col}{row}"] = f"Copied from {proj_col}{row} (PROJECTED) — no reliable Plaid signal for this line (2026-07-29)."
    notes_to_clear = [f"{col}{row}" for col, row, _ in missing]
    if notes_to_set:
        ws.update_notes(notes_to_set)
    if notes_to_clear:
        ws.clear_notes(notes_to_clear)

    print(f"  {action} '{tab_name}': wrote {len(cell_values)} line items, zeroed {len(missing)} with no data this month, "
          f"fixed {len(FIXED_CELLS)} cells, copied {len(copy_updates)} projected->actual, set {len(notes_to_set)} notes, cleared {len(notes_to_clear)} notes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", nargs="*", default=["2026-04", "2026-05", "2026-06", "2026-07"],
                         help="year_month values (YYYY-MM) to create tabs for")
    parser.add_argument("--dry-run", action="store_true", help="preview without writing or needing credentials")
    parser.add_argument("--year-months", nargs="*", default=None,
                         help="year_month values (YYYY-MM) to roll up into one yearly tab, "
                              "summed from each month's own tab -- skips the regular monthly sync")
    parser.add_argument("--year-tab-name", default=None, help="override the yearly tab's name")
    args = parser.parse_args()

    gc_spreadsheet = None
    if not args.dry_run:
        import gspread
        gc = gspread.service_account(filename=CREDENTIALS_PATH)
        gc_spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    if args.year_months:
        tab_name = args.year_tab_name or year_tab_name(args.year_months)
        print(f"\n{tab_name}:")
        sync_year(gc_spreadsheet, tab_name, args.year_months, args.dry_run)
        return

    df = load_all_transactions()

    all_needs_review: dict[str, list] = defaultdict(lambda: [0.0, 0])
    for year_month in args.months:
        print(f"\n{month_tab_name(year_month)} ({year_month}):")
        cell_values, cell_notes, needs_review = aggregate_month(df, year_month)
        for col_row, amount in sorted(cell_values.items(), key=lambda kv: kv[0][1]):
            print(f"  {col_row[0]}{col_row[1]}: {amount:>10,.2f}")
        for category, (amount, count) in sorted(needs_review.items(), key=lambda kv: -kv[1][0]):
            print(f"  [NEEDS REVIEW] {category}: ${amount:,.2f} ({count} txns) — not written to sheet")
            all_needs_review[category][0] += amount
            all_needs_review[category][1] += count

        sync_month(gc_spreadsheet, year_month, cell_values, cell_notes, args.dry_run)

    if all_needs_review:
        print("\n=== Needs review across all months (not written to any tab) ===")
        for category, (amount, count) in sorted(all_needs_review.items(), key=lambda kv: -kv[1][0]):
            print(f"  {category}: ${amount:,.2f} ({count} txns)")


if __name__ == "__main__":
    main()
