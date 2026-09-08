"""
budget_aggregate.py — shared category-resolution core for turning a month of
Plaid transactions into budget line items.

_resolve_month() is the single place the business rules live (UTILITIES
electric/gas splitting, NEEDS_REVIEW routing, hierarchical category
fallback, the Zus paycheck/Managed-Brokerages netting) — extracted from what
was previously sheets_sync.aggregate_month's body so the rules can't
silently drift between the Google Sheet sync and the API. Two adapters
consume it:

- sheets_sync.aggregate_month — Google Sheet (col, row) cell coordinates
  (unchanged output, see that module).
- aggregate_month_json (this module) — nested JSON for the web API,
  including full per-transaction detail (needed so the UI can list/
  recategorize individual transactions, including ones in NEEDS_REVIEW
  categories — sheets_sync never needed that detail since needs_review is
  only ever printed, not written to a cell).
"""

from collections import defaultdict
from datetime import datetime

import pandas as pd

import budget_schema
import custom_categories
import overrides
from sheet_category_map import CATEGORY_TO_LINE_ITEM, IGNORE_CATEGORIES, IGNORED_CATEGORY, NEEDS_REVIEW_CATEGORIES


def _txn_dict(row: pd.Series, category: str, date: str, description: str, amount: float) -> dict:
    return {
        "date": date,
        "description": description,
        "amount": amount,
        "account": row.get("account"),
        "transaction_id": row.get("transaction_id"),
        "category": category,
    }


def _resolve_month(df: pd.DataFrame, year_month: str) -> tuple[dict, dict, dict]:
    """
    Returns (line_item_totals, line_item_txns, needs_review_txns) for one
    year_month ("YYYY-MM"):
    - line_item_totals: {(section, line_item): total_amount}
    - line_item_txns: {(section, line_item): [txn_dict, ...]}
    - needs_review_txns: {category: [txn_dict, ...]} — categories in
      NEEDS_REVIEW_CATEGORIES or with no mapping at all (prefixed
      "UNMAPPED:"), excluded from line_item_totals entirely.
    """
    month_df = df[df["year_month"] == year_month]
    month_df = month_df[~month_df["category"].isin(IGNORE_CATEGORIES)]

    # CATEGORY_TO_LINE_ITEM alone is the static, hardcoded dict — merge in
    # custom_categories.py's runtime-persisted additions (from the "add a
    # new category" UI, see api_server.POST /api/categories) so a category
    # created through that flow resolves to its chosen section/line item
    # here too, rather than immediately falling into UNMAPPED needs_review
    # the moment it's assigned to a transaction (2026-08-01 fix — caught
    # live: /api/categories knew about the new category, but this function
    # still only ever consulted the static dict).
    category_to_line_item = {**CATEGORY_TO_LINE_ITEM, **custom_categories.list_custom_categories()}

    line_item_totals: dict[tuple[str, str], float] = defaultdict(float)
    line_item_txns: dict[tuple[str, str], list] = defaultdict(list)
    needs_review_txns: dict[str, list] = defaultdict(list)

    def record(section, line_item, txn):
        line_item_totals[(section, line_item)] += txn["amount"]
        line_item_txns[(section, line_item)].append(txn)

    for _, row in month_df.iterrows():
        category = row["category"]
        amount = float(row["amount"])
        date, description = row["date"], row["description"]
        # National Grid bills electric+gas on one statement — Plaid gives no
        # way to split them, so divide 50/50 between the sheet's two lines
        # rather than leaving a big, easily-avoidable gap. Other UTILITIES
        # vendors (PPL, one-off payment fees, ...) fall back to HOME > Other.
        if category == "UTILITIES":
            if "national grid" in str(description).lower():
                half_note = f"{description} (1/2 of ${amount:,.2f} bill)"
                record("HOME", "Electricity (Nat'l grid)", _txn_dict(row, category, date, half_note, amount / 2))
                record("HOME", "Gas (Nat'l grid)", _txn_dict(row, category, date, half_note, amount / 2))
            else:
                record("HOME", "Other", _txn_dict(row, category, date, description, amount))
            continue
        if category in NEEDS_REVIEW_CATEGORIES:
            needs_review_txns[category].append(_txn_dict(row, category, date, description, amount))
            continue
        # "FOOD RESTAURANTS"/"FOOD GROCERIES" etc. encode the second word as a
        # subcategory of the first (see CLAUDE.md). Prefer the more specific
        # subcategory when it has its own mapping (e.g. "FOOD GROCERIES" must
        # resolve to GROCERIES -> Groceries, not fall through to FOOD ->
        # Dining Out just because the parent happens to be mapped too); only
        # fall back to the parent (first word) if the subcategory isn't
        # separately mapped (2026-07-29 — Stop & Shop/Target/Walmart were
        # wrongly landing in Dining Out via the FOOD parent).
        mapping = (
            category_to_line_item.get(category)
            or category_to_line_item.get(category.split(" ")[-1])
            or category_to_line_item.get(category.split(" ")[0])
        )
        if mapping is None:
            needs_review_txns[f"UNMAPPED:{category}"].append(_txn_dict(row, category, date, description, amount))
            continue
        section, line_item = mapping
        record(section, line_item, _txn_dict(row, category, date, description, amount))

    return dict(line_item_totals), dict(line_item_txns), dict(needs_review_txns)


def _hidden_transactions_for_month(df: pd.DataFrame, year_month: str) -> list[dict]:
    """Transactions in a SYSTEM-recognized transfer/payment category
    (IGNORE_CATEGORIES minus IGNORED_CATEGORY, which is the separate
    user-driven "Ignore this transaction" feature — see
    _ignored_transactions_for_month) — self-transfers, credit card
    payments, Venmo payments, boilerplate noise. _resolve_month excludes
    these from every total the same way it excludes IGNORED_CATEGORY, but
    unlike that feature they were previously invisible everywhere, with no
    way to confirm a transaction landed here correctly rather than being
    miscategorized (2026-08-02, user-reported: "I still need to be able to
    see hidden transactions"). Bucketed by category, same shape as
    needs_review_txns, so the frontend can reuse the same rendering."""
    hidden_categories = IGNORE_CATEGORIES - {IGNORED_CATEGORY}
    month_df = df[(df["year_month"] == year_month) & (df["category"].isin(hidden_categories))]
    buckets: dict[str, list[dict]] = defaultdict(list)
    for _, row in month_df.iterrows():
        category = row["category"]
        buckets[category].append(_txn_dict(row, category, row["date"], row["description"], float(row["amount"])))
    return [
        {
            "category": category,
            "amount": round(sum(t["amount"] for t in items), 2),
            "count": len(items),
            "transactions": items,
        }
        for category, items in buckets.items()
    ]


def _ignored_transactions_for_month(df: pd.DataFrame, year_month: str) -> list[dict]:
    """Transactions the user explicitly marked ignored via the dashboard's
    "Ignore this transaction" action. IGNORED_CATEGORY is part of
    IGNORE_CATEGORIES, so _resolve_month above already excludes these from
    every total and the Sankey diagram — this just surfaces them (with the
    user's note) for the dashboard's dedicated Ignored section, purely for
    observation/potential later re-categorization (2026-08-02, user-specified:
    "NOT in the sankey diagram nor ... final amounts, only for observation")."""
    month_df = df[(df["year_month"] == year_month) & (df["category"] == IGNORED_CATEGORY)]
    notes = overrides.list_ignored_transactions()
    return [
        {
            "date": row["date"],
            "description": row["description"],
            "amount": float(row["amount"]),
            "account": row.get("account"),
            "transaction_id": row.get("transaction_id"),
            "category": IGNORED_CATEGORY,
            "note": notes.get(row.get("transaction_id"), {}).get("note"),
        }
        for _, row in month_df.iterrows()
    ]


def format_cell_note(txns: list[dict]) -> str:
    """Tab-separated per-transaction breakdown text, matching the Google
    Sheet cell-note format sheets_sync.py has always written."""
    lines = []
    for t in sorted(txns, key=lambda t: (t["date"] is None, t["date"])):
        if t["date"] is None:
            lines.append(t["description"])
        else:
            d = datetime.strptime(t["date"], "%Y-%m-%d").strftime("%m/%d/%Y")
            lines.append(f"{d}\t{t['amount']:,.2f}\t{t['description']}\t{t['account']}")
    return "\n".join(lines)


def aggregate_month_json(
    df: pd.DataFrame,
    year_month: str,
    sections: tuple[budget_schema.Section, ...] = budget_schema.BUDGET_SECTIONS,
    projected: dict[tuple[str, str], float] | None = None,
) -> dict:
    """
    Nested JSON view of one month for the web API:
    {year_month, sections: [{key, label, kind, line_items: [...], other: {...}?}], needs_review: [...], ignored: [...], hidden: [...]}

    `projected` is {(section_key, line_item_label): value}, typically from
    budget_sheets.fetch_projected_values(year_month) — pass None (the
    default) to omit PROJECTED/DIFFERENCE entirely (e.g. for the
    Sankeymatic endpoint, which only needs actuals and shouldn't wait on a
    Sheets API call).
    """
    totals, txns, needs_review_txns = _resolve_month(df, year_month)

    def line_item_entry(key: tuple[str, str], label: str, row: int, fixed_value: float | None = None, copy_projected: bool = False) -> dict:
        proj = projected.get(key) if projected is not None else None
        # Line items with no reliable Plaid signal don't use the raw
        # category-derived total at all — same rule the Google Sheet sync
        # applies (sheets_sync.FIXED_CELLS / COPY_PROJECTED_CELLS): a fixed
        # line item is always its constant, and a copy-projected line item's
        # ACTUAL always mirrors PROJECTED (not whatever Plaid happens to
        # produce for that category, which may be real money but isn't the
        # right money for this specific line — e.g. Retirement 401k/IRA
        # contributions are invisible payroll deductions Plaid never sees).
        if fixed_value is not None:
            actual = fixed_value
        elif copy_projected:
            actual = proj if proj is not None else 0.0
        else:
            actual = round(totals.get(key, 0.0), 2)
        return {
            "label": label,
            "row": row,
            "projected": proj,
            "actual": actual,
            "difference": (round(actual - proj, 2) if proj is not None else None),
            "is_fixed": fixed_value is not None,
            "is_copy_projected": copy_projected,
            "transactions": [] if (fixed_value is not None or copy_projected) else txns.get(key, []),
        }

    result_sections = []
    for s in sections:
        entry = {
            "key": s.key,
            "label": s.label,
            "kind": s.kind,
            "line_items": [
                line_item_entry((s.key, li.label), li.label, li.row, li.fixed_value, li.copy_projected)
                for li in s.line_items
            ],
        }
        if s.other_row is not None:
            entry["other"] = line_item_entry((s.key, "Other"), "Other", s.other_row)
        result_sections.append(entry)

    needs_review = [
        {
            "category": cat,
            "amount": round(sum(t["amount"] for t in items), 2),
            "count": len(items),
            "transactions": items,
        }
        for cat, items in needs_review_txns.items()
    ]

    # CATEGORY_TO_LINE_ITEM (plus custom_categories.py's runtime additions)
    # can point a category at a (section, line_item) pair that isn't one of
    # that section's fixed rows in budget_schema.BUDGET_SECTIONS — this is
    # always a custom category (a brand-new subcategory added through the
    # "add a category" UI, see POST /api/categories in api_server.py) that
    # has no actual row in the Google Sheet yet; CATEGORY_TO_LINE_ITEM's own
    # static entries always point at a real schema LineItem by construction.
    #
    # Give it a real, distinctly-named entry in its section — folding it
    # into the section's generic "Other" bucket (an earlier version of this
    # fix did that) throws away the very name the user just chose, which
    # defeats the point of adding a named category at all; and sections with
    # no "Other" row at all (Savings, Transportation, Health) had nowhere to
    # put it, so the money just vanished into needs_review forever, stuck as
    # an "UNMAPPED:section / label" entry the user had no reason to think to
    # check (2026-08-01 fix — caught live: a transaction recategorized to a
    # new custom Savings subcategory disappeared from both the sidebar and
    # the diagram).
    #
    # `row` has no real Google Sheet cell to point at (sheets_sync.py never
    # sees these — aggregate_month_json is API/dashboard-only), so synthetic
    # entries get descending negative rows; nothing here treats row as
    # anything but a stable React list key.
    known_keys = {(s.key, li.label) for s in sections for li in s.line_items}
    known_keys |= {(s.key, "Other") for s in sections if s.other_row is not None}
    result_section_by_key = {entry["key"]: entry for entry in result_sections}
    next_synthetic_row = -1
    for key, amount in totals.items():
        if key in known_keys:
            continue
        section_key, line_item_label = key
        section_entry = result_section_by_key.get(section_key)
        if section_entry is None:
            # Resolves to a section this call wasn't even asked to render
            # (shouldn't happen — `sections` always covers the full schema —
            # but fail safe into needs_review rather than silently dropping
            # the money).
            needs_review.append({
                "category": f"UNMAPPED:{section_key} / {line_item_label}",
                "amount": round(amount, 2),
                "count": len(txns.get(key, [])),
                "transactions": txns.get(key, []),
            })
            continue
        section_entry["line_items"].append(line_item_entry(key, line_item_label, next_synthetic_row))
        next_synthetic_row -= 1

    ignored = _ignored_transactions_for_month(df, year_month)
    hidden = _hidden_transactions_for_month(df, year_month)

    return {
        "year_month": year_month, "sections": result_sections,
        "needs_review": needs_review, "ignored": ignored, "hidden": hidden,
    }


# Rolling lookback windows the dashboard offers alongside single-month mode.
# "YTD" isn't a fixed month count (it depends on the anchor month), so it's
# handled separately in compute_range_months rather than living in this dict.
RANGE_MONTH_COUNTS: dict[str, int] = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}
VALID_RANGE_KEYS: tuple[str, ...] = tuple(RANGE_MONTH_COUNTS) + ("YTD",)


def compute_range_months(available_months: list[str], range_key: str, end_year_month: str) -> list[str]:
    """
    Given the sorted list of year_months that actually have data (e.g. from
    `sorted(df["year_month"].dropna().unique())`, the same source
    /api/months already uses), a range_key ("1M"/"3M"/"6M"/"1Y"/"YTD"), and
    an anchor end_year_month (the currently-selected/default month — the
    same one single-month mode would show), return the ordered list of
    year_months to sum for that range.

    - "1M"/"3M"/"6M"/"1Y": the N most-recently-*available* months up to and
      including end_year_month, walking backward through `available_months`
      — NOT N calendar months back. If Plaid data has a gap (a month with
      zero synced activity), this still returns N months of real data
      rather than silently padding in an all-zero month. If fewer than N
      months of data exist at or before the anchor, returns whatever's
      available (a short range, not an error).
    - "YTD": every available month in the same calendar year as
      end_year_month, from January through end_year_month inclusive. The
      anchor's *year* — not the real wall-clock year — defines "current".
      This is a deliberate judgment call: it keeps a bookmarked/shared YTD
      URL for a past month stable (reopening it later doesn't silently
      jump to a different year), and it matches how every other range kind
      is anchored on the selected month rather than on a live "today" that
      changes underneath a returning user. The alternative (always the
      real current year) would make "YTD" drift for anyone revisiting an
      old bookmark.

    Raises ValueError if end_year_month isn't in available_months or
    range_key isn't recognized — callers (the API layer) should turn that
    into a 400.
    """
    if end_year_month not in available_months:
        raise ValueError(f"end_year_month {end_year_month!r} not in available_months")
    if range_key not in VALID_RANGE_KEYS:
        raise ValueError(f"unknown range_key {range_key!r}; must be one of {VALID_RANGE_KEYS}")

    end_index = available_months.index(end_year_month)
    if range_key == "YTD":
        year = end_year_month[:4]
        return [ym for ym in available_months[: end_index + 1] if ym[:4] == year]

    n = RANGE_MONTH_COUNTS[range_key]
    start_index = max(0, end_index - n + 1)
    return available_months[start_index : end_index + 1]


def aggregate_range_json(
    df: pd.DataFrame,
    year_months: list[str],
    sections: tuple[budget_schema.Section, ...] = budget_schema.BUDGET_SECTIONS,
    projected_by_month: dict[str, dict[tuple[str, str], float] | None] | None = None,
) -> dict:
    """
    Sums N consecutive months into the *same nested JSON shape*
    aggregate_month_json returns for one month (`sections`, `needs_review`
    — everything except `year_month`, replaced here with `year_months`), so
    every downstream consumer — budget_sankeymatic.to_sankeymatic, the
    API's totals computation, the frontend's BudgetSection/
    BudgetLineItemRow/NotesDrawer — needs zero changes to render a range.

    Implementation: call aggregate_month_json once per month (reusing every
    bit of _resolve_month's category-resolution business logic — the
    UTILITIES 50/50 split, NEEDS_REVIEW routing, hierarchical category
    fallback, Zus/brokerage netting, fixed/copy-projected handling — rather
    than re-deriving any of it here) and sum the per-line-item actual/
    projected/difference across months.

    PROJECTED for a range (judgment call, not derived from the data):
    PROJECTED targets are inherently monthly — one Google Sheet tab per
    month, no single "3-month target" cell exists to read. This function
    defines a range's PROJECTED as the SUM of each contained month's
    PROJECTED (the natural reading of "did I hit my budget for this
    span"), treating a month with no sheet tab at all as contributing $0
    rather than making the whole range's PROJECTED unavailable — UNLESS
    *no* month in the range has a sheet tab, in which case PROJECTED (and
    DIFFERENCE) come back None for that line item, same as single-month
    mode's "no sheet tab" behavior. `projected_by_month` is
    {year_month: {(section_key, line_item_label): value} | None}, keyed
    exactly like budget_sheets.fetch_projected_values's return per month —
    pass None (the default) to omit PROJECTED entirely, same as
    aggregate_month_json.

    needs_review is unioned by category across all months (transactions
    concatenated, amount/count re-summed) so nothing silently disappears
    for a range that single-month mode would have flagged.
    """
    if not year_months:
        raise ValueError("year_months must be non-empty")

    per_month = [
        aggregate_month_json(df, ym, sections=sections, projected=(projected_by_month or {}).get(ym))
        for ym in year_months
    ]

    def merge_entries(entries: list[dict]) -> dict:
        projected_vals = [e["projected"] for e in entries if e["projected"] is not None]
        projected = round(sum(projected_vals), 2) if projected_vals else None
        actual = round(sum(e["actual"] for e in entries), 2)
        return {
            "label": entries[0]["label"],
            "row": entries[0]["row"],
            "projected": projected,
            "actual": actual,
            "difference": round(actual - projected, 2) if projected is not None else None,
            "is_fixed": entries[0]["is_fixed"],
            "is_copy_projected": entries[0]["is_copy_projected"],
            "transactions": [t for e in entries for t in e["transactions"]],
        }

    result_sections = []
    for si, s in enumerate(sections):
        month_sections = [pm["sections"][si] for pm in per_month]

        # Merge by LABEL, not by list index/position. Static line items
        # always appear in every month's list at the same position, but a
        # SYNTHETIC/stray entry (a custom category with no schema row — see
        # aggregate_month_json's next_synthetic_row) only appears in
        # whichever months actually had a transaction in it, so per-month
        # line_items lists can differ in length and order once any custom
        # category/section is in play. Index-based merging silently
        # dropped or misaligned these entries (2026-08-02 fix, found while
        # adding custom top-level sections — a brand-new section's ENTIRE
        # line item list is synthetic, so this bug would have hidden every
        # custom section's data in range mode as soon as one existed).
        label_order: list[str] = []
        row_by_label: dict[str, int] = {}
        entries_by_label: dict[str, list[dict]] = defaultdict(list)
        for ms in month_sections:
            for li in ms["line_items"]:
                if li["label"] not in row_by_label:
                    label_order.append(li["label"])
                    row_by_label[li["label"]] = li["row"]
                entries_by_label[li["label"]].append(li)

        def placeholder(label: str) -> dict:
            # A month where this (necessarily synthetic — static entries
            # are present every month by construction) entry had no
            # transactions at all.
            return {
                "label": label, "row": row_by_label[label], "projected": None, "actual": 0.0,
                "difference": None, "is_fixed": False, "is_copy_projected": False, "transactions": [],
            }

        line_items = [
            merge_entries(entries_by_label[label] + [placeholder(label)] * (len(month_sections) - len(entries_by_label[label])))
            for label in label_order
        ]
        entry = {"key": s.key, "label": s.label, "kind": s.kind, "line_items": line_items}
        if s.other_row is not None:
            entry["other"] = merge_entries([ms["other"] for ms in month_sections])
        result_sections.append(entry)

    needs_review_map: dict[str, dict] = {}
    for pm in per_month:
        for bucket in pm["needs_review"]:
            slot = needs_review_map.setdefault(bucket["category"], {"category": bucket["category"], "transactions": []})
            slot["transactions"].extend(bucket["transactions"])
    needs_review = [
        {
            "category": slot["category"],
            "amount": round(sum(t["amount"] for t in slot["transactions"]), 2),
            "count": len(slot["transactions"]),
            "transactions": slot["transactions"],
        }
        for slot in needs_review_map.values()
    ]

    # Concatenated, not deduped/summed like needs_review's per-category
    # buckets — each ignored transaction is already a standalone observation
    # entry, not a total that could double-count across months.
    ignored = [t for pm in per_month for t in pm["ignored"]]

    hidden_map: dict[str, dict] = {}
    for pm in per_month:
        for bucket in pm["hidden"]:
            slot = hidden_map.setdefault(bucket["category"], {"category": bucket["category"], "transactions": []})
            slot["transactions"].extend(bucket["transactions"])
    hidden = [
        {
            "category": slot["category"],
            "amount": round(sum(t["amount"] for t in slot["transactions"]), 2),
            "count": len(slot["transactions"]),
            "transactions": slot["transactions"],
        }
        for slot in hidden_map.values()
    ]

    return {
        "year_months": year_months, "sections": result_sections,
        "needs_review": needs_review, "ignored": ignored, "hidden": hidden,
    }
