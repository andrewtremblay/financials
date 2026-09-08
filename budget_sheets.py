"""
budget_sheets.py — read-only access to PROJECTED (budget target) values from
the Google Sheet, for the web API. ACTUAL is always computed locally from
Plaid data (see budget_aggregate.py) — this module never writes anything to
the sheet (that's still sheets_sync.py's job).

gspread calls are slow and rate-limited, so results are cached in-process
with a short TTL — a user flipping through months in one browsing session
shouldn't re-hit the Sheets API on every click. Both list_sheet_tabs() and
fetch_projected_values() degrade gracefully (empty list / None) on any
Sheets/auth failure rather than raising, so a broken or expired
service_account.json takes down PROJECTED display only, not the whole
dashboard.
"""

import time

import gspread

import budget_schema
from sheets_sync import CREDENTIALS_PATH, SPREADSHEET_ID, month_tab_name

_TTL_SECONDS = 300

_client = None
_tab_cache: tuple[float, list[str]] | None = None
_projected_cache: dict[str, tuple[float, dict | None]] = {}


def _get_client():
    global _client
    if _client is None:
        _client = gspread.service_account(filename=CREDENTIALS_PATH)
    return _client


def _spreadsheet():
    return _get_client().open_by_key(SPREADSHEET_ID)


def list_sheet_tabs() -> list[str]:
    global _tab_cache
    if _tab_cache and time.time() - _tab_cache[0] < _TTL_SECONDS:
        return _tab_cache[1]
    try:
        titles = [ws.title for ws in _spreadsheet().worksheets()]
    except Exception:
        return _tab_cache[1] if _tab_cache else []
    _tab_cache = (time.time(), titles)
    return titles


def _fetch_from_sheet(tab_name: str, sections: tuple[budget_schema.Section, ...]) -> dict[tuple[str, str], float | None]:
    ws = _spreadsheet().worksheet(tab_name)
    cell_keys: list[tuple[str, str]] = []
    cell_refs: list[str] = []
    for s in sections:
        for li in s.line_items:
            cell_keys.append((s.key, li.label))
            cell_refs.append(f"{s.projected_column}{li.row}")
        if s.other_row is not None:
            cell_keys.append((s.key, "Other"))
            cell_refs.append(f"{s.projected_column}{s.other_row}")

    values = ws.batch_get(cell_refs, value_render_option="UNFORMATTED_VALUE")
    result: dict[tuple[str, str], float | None] = {}
    for key, vals in zip(cell_keys, values):
        v = vals[0][0] if vals and vals[0] else None
        result[key] = float(v) if isinstance(v, (int, float)) else None
    return result


def fetch_projected_values(
    year_month: str,
    sections: tuple[budget_schema.Section, ...] = budget_schema.BUDGET_SECTIONS,
) -> dict[tuple[str, str], float] | None:
    """
    {(section_key, line_item_label): projected_value} for one month, or None
    if there's no sheet tab for this month, or the Sheets API call fails for
    any reason. Callers should treat None as "PROJECTED not available this
    month" and still render ACTUAL — never let this block the dashboard.
    """
    cached = _projected_cache.get(year_month)
    if cached and time.time() - cached[0] < _TTL_SECONDS:
        return cached[1]

    tab_name = month_tab_name(year_month)
    if tab_name not in list_sheet_tabs():
        result = None
    else:
        try:
            result = _fetch_from_sheet(tab_name, sections)
        except Exception:
            result = None

    _projected_cache[year_month] = (time.time(), result)
    return result
