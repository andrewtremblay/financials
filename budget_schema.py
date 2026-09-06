"""
budget_schema.py — explicit, ordered description of the household budget
sheet's section/line-item hierarchy (income, savings, and six expense
sections: HOME, TRANSPORTATION, DAILY LIVING, ENTERTAINMENT, HEALTH,
VACATION / HOLIDAY).

Previously this hierarchy only existed implicitly as row-number gaps in
sheets_sync.py's flat INCOME_SAVINGS_ROWS/EXPENSE_ROWS/EXPENSE_OTHER_ROWS
dicts. This module is the single source of truth; sheets_sync.py derives
those dicts from it (see income_savings_rows(), expense_rows(),
expense_other_rows(), fixed_cells(), copy_projected_cells() below), and the
new budget_aggregate/api_server modules use BUDGET_SECTIONS directly for a
nested JSON representation.

Row numbers, PROJECTED/ACTUAL column letters, fixed values, and
copy-projected line items are transcribed from sheets_sync.py's prior
hardcoded dicts (verified 2026-07-29) — a month tab's row layout is
identical across every existing month.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LineItem:
    # Must match the corresponding value in sheet_category_map.CATEGORY_TO_LINE_ITEM
    # byte-for-byte — that's the coupling between category mapping and sheet layout.
    label: str
    row: int
    # Forced to this exact value every sync, both PROJECTED and ACTUAL, regardless
    # of Plaid data (currently just Apartment Rental Income — see sheets_sync.FIXED_CELLS).
    fixed_value: float | None = None
    # ACTUAL mirrors whatever PROJECTED says (read live each sync) — for line items
    # funded from untracked accounts or untraceable payment methods.
    copy_projected: bool = False


@dataclass(frozen=True)
class Section:
    # "income" / "savings" for the income/savings side; the expense group name
    # (matching sheet_category_map.CATEGORY_TO_LINE_ITEM's section values) otherwise.
    key: str
    label: str
    kind: str  # "income_savings" | "expense"
    actual_column: str  # "D" for income/savings, "J" for expenses
    line_items: tuple[LineItem, ...]
    # Row of this section's "Other" catch-all line, if it has one (not every
    # expense section does — TRANSPORTATION and HEALTH have no "Other" row).
    other_row: int | None = None

    @property
    def projected_column(self) -> str:
        return "C" if self.actual_column == "D" else "I"


BUDGET_SECTIONS: tuple[Section, ...] = (
    Section("income", "Income", "income_savings", "D", (
        LineItem("Take Home Salary (Zus)", 4),
        LineItem("Take Home Salary (Banneker)", 5),
        LineItem("Interest Income", 6),
        LineItem("Dividends", 7),
        LineItem("Refunds / Reimbursements", 8),
        LineItem("Apartment Rental Income", 9, fixed_value=2275.00),
        LineItem("Misc.", 10),
    )),
    Section("savings", "Savings", "income_savings", "D", (
        LineItem("Emergency Fund", 16, copy_projected=True),
        LineItem("Retirement (MTRS)", 17, copy_projected=True),
        LineItem("Retirement (401k + Match)", 18, copy_projected=True),
        LineItem("Managed Brokerages", 19),
        LineItem("Home Projects (Apt. Rent)", 20, copy_projected=True),
        LineItem("Other Savings", 21),
    )),
    Section("HOME", "Home", "expense", "J", (
        LineItem("Mortgage (12 Warren)", 4),
        LineItem("Mortgage + HOA (1 Cityview)", 5),
        LineItem("Home / Rental Insurance", 6),
        LineItem("Electricity (Nat'l grid)", 7),
        LineItem("Gas (Nat'l grid)", 8),
        LineItem("Water / Sewer", 9),
        LineItem("Phone (AT&T)", 10),
        LineItem("Internet (Xfinity)", 11),
        LineItem("Furnishing / Appliances", 12),
        LineItem("Lawn / Garden", 13),
        LineItem("Maintenance / Improvements", 14),
    ), other_row=15),
    Section("TRANSPORTATION", "Transportation", "expense", "J", (
        LineItem("Registration / License", 18),
        LineItem("Auto Insurance", 19),
        LineItem("Fuel", 20),
        LineItem("Public Transportation", 21),
        LineItem("Repairs / Maintenance", 22),
        LineItem("Motor Vehicle Excise Tax", 23),
    ), other_row=None),
    Section("DAILY LIVING", "Daily Living", "expense", "J", (
        LineItem("Groceries", 26),
        LineItem("Dining Out", 27),
        LineItem("Clothing", 28),
        LineItem("Cleaning Service", 29, copy_projected=True),
        LineItem("Hair & Nail Salon / Barber", 30),
        LineItem("Gifts", 31),
    ), other_row=32),
    Section("ENTERTAINMENT", "Entertainment", "expense", "J", (
        LineItem("Streaming / Movies", 35),
        LineItem("Concerts / Plays", 36),
        LineItem("Sports", 37),
    ), other_row=38),
    Section("HEALTH", "Health", "expense", "J", (
        LineItem("Health Insurance", 41),
        LineItem("Gym Membership", 42),
        LineItem("Doctors / Dentist Visits", 43),
        LineItem("Medicine / Prescriptions", 44),
        LineItem("Car Insurance", 45),
        LineItem("Umbrella Insurance", 46),
    ), other_row=None),
    Section("VACATION / HOLIDAY", "Vacation / Holiday", "expense", "J", (
        LineItem("Airfare", 49),
        LineItem("Accommodations", 50),
        LineItem("Food", 51),
        LineItem("Souvenirs", 52),
        LineItem("Rental Car / Ubers", 53),
    ), other_row=54),
)


def income_savings_rows(sections: tuple[Section, ...] = BUDGET_SECTIONS) -> dict[str, int]:
    return {li.label: li.row for s in sections if s.kind == "income_savings" for li in s.line_items}


def expense_rows(sections: tuple[Section, ...] = BUDGET_SECTIONS) -> dict[str, int]:
    return {li.label: li.row for s in sections if s.kind == "expense" for li in s.line_items}


def expense_other_rows(sections: tuple[Section, ...] = BUDGET_SECTIONS) -> dict[str, int]:
    return {s.key: s.other_row for s in sections if s.kind == "expense" and s.other_row is not None}


def fixed_cells(sections: tuple[Section, ...] = BUDGET_SECTIONS) -> dict[tuple[str, int], float]:
    cells: dict[tuple[str, int], float] = {}
    for s in sections:
        for li in s.line_items:
            if li.fixed_value is not None:
                cells[(s.projected_column, li.row)] = li.fixed_value
                cells[(s.actual_column, li.row)] = li.fixed_value
    return cells


def copy_projected_cells(sections: tuple[Section, ...] = BUDGET_SECTIONS) -> dict[tuple[str, int], str]:
    """{(actual_col, row): projected_col} for every copy_projected line item."""
    return {
        (s.actual_column, li.row): s.projected_column
        for s in sections for li in s.line_items if li.copy_projected
    }
