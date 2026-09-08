"""
api_server.py — FastAPI backend for the browser budget dashboard.

Serves month/section/line-item data (ACTUAL from Plaid via
budget_aggregate.py, PROJECTED live from the Google Sheet via
budget_sheets.py), a Sankeymatic diagram string, a needs-review queue, and
recategorization endpoints (per-transaction override + merchant-wide rule,
both backed by overrides.py and durable across the next plaid_sync.py run).

Dev:
    uv run uvicorn api_server:app --reload --port 8000
    (separately: cd frontend_react && npm run dev, talks to this over CORS)

"Production" (still local-only, single process, no CORS needed):
    cd frontend_react && npm run build
    uv run uvicorn api_server:app --port 8000
"""

import glob
import os
import re
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import budget_classification
import budget_rules
import budget_sankeymatic
import budget_sheets
import custom_budget_classification
import custom_categories
import custom_sections
import overrides
import plaid_client
import retirement_engine
import retirement_settings
import untracked_income
from budget_aggregate import aggregate_month_json, aggregate_range_json, compute_range_months
from budget_schema import BUDGET_SECTIONS, Section
from sheet_category_map import CATEGORY_TO_LINE_ITEM
from sheets_sync import load_all_transactions, month_tab_name

app = FastAPI(title="Financials Budget API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def last_complete_month(today: date | None = None) -> str:
    """Always the previous calendar month relative to today, regardless of
    what day of the current month it is (the current month is never
    "complete" until it's over)."""
    today = today or date.today()
    first_of_this_month = today.replace(day=1)
    return (first_of_this_month - timedelta(days=1)).strftime("%Y-%m")


@app.get("/api/months")
def list_months():
    df = load_all_transactions()
    months = sorted(df["year_month"].dropna().unique().tolist())
    sheet_tabs = set(budget_sheets.list_sheet_tabs())
    return {
        "months": [
            {"year_month": ym, "label": month_tab_name(ym), "has_sheet_tab": month_tab_name(ym) in sheet_tabs}
            for ym in months
        ],
        "default_year_month": last_complete_month(),
    }


def _all_sections() -> tuple[Section, ...]:
    """BUDGET_SECTIONS (static) plus a synthetic Section for every
    custom_sections.py entry — a brand-new top-level section the user
    created directly, not just a subcategory within an existing one (see
    custom_sections.py's docstring). Passed as the `sections` argument to
    every aggregate_month_json/aggregate_range_json call in this file, so a
    category assigned to a custom section resolves into its own real
    section entry via the SAME stray-key synthesis that already handles a
    custom category with no schema row, rather than falling into
    needs_review as "a section this call wasn't even asked to render"
    (2026-08-02, user-requested: "I want to be able to create new
    sections, not just sub-sections").

    actual_column="J" (the expense-section convention) is a placeholder —
    custom sections are dashboard-only and never synced to the Google
    Sheet, so this value is never actually read for them."""
    custom = tuple(
        Section(key=key, label=label, kind="expense", actual_column="J", line_items=())
        for key, label in custom_sections.list_custom_sections().items()
    )
    return BUDGET_SECTIONS + custom


def _compute_totals(month_json: dict) -> dict:
    """{income, savings, expense, net} from an aggregate_month_json/
    aggregate_range_json result — shared by the single-month and range
    endpoints so the income/savings/expense/net rollup rule can't drift
    between them."""
    totals = {"income": 0.0, "savings": 0.0, "expense": 0.0}
    for section in month_json["sections"]:
        items = list(section["line_items"]) + ([section["other"]] if section.get("other") else [])
        section_total = sum(li["actual"] for li in items)
        if section["kind"] == "income_savings":
            totals["income" if section["key"] == "income" else "savings"] += section_total
        else:
            totals["expense"] += section_total
    totals["net"] = round(totals["income"] - totals["expense"] - totals["savings"], 2)
    return totals


@app.get("/api/months/{year_month}")
def get_month(year_month: str):
    df = load_all_transactions()
    projected = budget_sheets.fetch_projected_values(year_month)
    month_json = aggregate_month_json(df, year_month, sections=_all_sections(), projected=projected)
    month_json["has_sheet_tab"] = projected is not None
    month_json["totals"] = _compute_totals(month_json)
    return month_json


@app.get("/api/months/{year_month}/sankeymatic")
def get_month_sankeymatic(year_month: str, group_by: str = "section"):
    if group_by not in budget_sankeymatic.GROUP_BY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"unknown group_by {group_by!r}; must be one of {budget_sankeymatic.GROUP_BY_OPTIONS}")
    df = load_all_transactions()
    # "copy_projected" line items (Emergency Fund, Retirement, Home Projects,
    # ...) only get a nonzero ACTUAL when PROJECTED is supplied — passing
    # None here silently dropped several real, sizeable savings flows from
    # the diagram entirely (2026-07-31 fix; found via a real month missing
    # ~$4,600 of savings nodes). The frontend always requests this alongside
    # /api/months/{ym}, which already primes budget_sheets' cache, so this
    # rarely triggers a fresh Sheets call in practice.
    projected = budget_sheets.fetch_projected_values(year_month)
    month_json = aggregate_month_json(df, year_month, sections=_all_sections(), projected=projected)
    return {"text": budget_sankeymatic.to_sankeymatic(month_json, group_by=group_by)}


def _resolve_range(range_key: str, end_year_month: str):
    """Shared by both range endpoints: loads transactions, resolves the
    range_key/end_year_month pair to a concrete list of year_months via
    compute_range_months, and turns an invalid range_key/anchor into a 400
    rather than a 500."""
    df = load_all_transactions()
    available_months = sorted(df["year_month"].dropna().unique().tolist())
    try:
        year_months = compute_range_months(available_months, range_key, end_year_month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return df, year_months


@app.get("/api/range/{range_key}/{end_year_month}")
def get_range(range_key: str, end_year_month: str):
    df, year_months = _resolve_range(range_key, end_year_month)
    projected_by_month = {ym: budget_sheets.fetch_projected_values(ym) for ym in year_months}
    range_json = aggregate_range_json(df, year_months, sections=_all_sections(), projected_by_month=projected_by_month)
    range_json["has_sheet_tab"] = any(p is not None for p in projected_by_month.values())
    range_json["totals"] = _compute_totals(range_json)
    return range_json


@app.get("/api/range/{range_key}/{end_year_month}/sankeymatic")
def get_range_sankeymatic(range_key: str, end_year_month: str, group_by: str = "section"):
    if group_by not in budget_sankeymatic.GROUP_BY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"unknown group_by {group_by!r}; must be one of {budget_sankeymatic.GROUP_BY_OPTIONS}")
    df, year_months = _resolve_range(range_key, end_year_month)
    # Same rationale as get_month_sankeymatic above: copy_projected line
    # items need PROJECTED supplied or their ACTUAL silently reads as $0.
    projected_by_month = {ym: budget_sheets.fetch_projected_values(ym) for ym in year_months}
    range_json = aggregate_range_json(df, year_months, sections=_all_sections(), projected_by_month=projected_by_month)
    return {"text": budget_sankeymatic.to_sankeymatic(range_json, group_by=group_by)}


@app.get("/api/months/{year_month}/budget-rules")
def get_month_budget_rules(year_month: str):
    df = load_all_transactions()
    # Same rationale as get_month_sankeymatic above: copy_projected line
    # items (retirement contributions, Emergency Fund, Home Projects) only
    # get a nonzero ACTUAL when PROJECTED is supplied — the Savings bucket
    # every rule below depends on would be badly undercounted without this.
    projected = budget_sheets.fetch_projected_values(year_month)
    month_json = aggregate_month_json(df, year_month, sections=_all_sections(), projected=projected)
    return {"rules": budget_rules.compute_all_rules(month_json)}


@app.get("/api/range/{range_key}/{end_year_month}/budget-rules")
def get_range_budget_rules(range_key: str, end_year_month: str):
    df, year_months = _resolve_range(range_key, end_year_month)
    projected_by_month = {ym: budget_sheets.fetch_projected_values(ym) for ym in year_months}
    range_json = aggregate_range_json(df, year_months, sections=_all_sections(), projected_by_month=projected_by_month)
    return {"rules": budget_rules.compute_all_rules(range_json)}


def _savings_line_items(month_json: dict) -> list[dict]:
    return next(s for s in month_json["sections"] if s["key"] == "savings")["line_items"]


@app.get("/api/months/{year_month}/untracked-income")
def get_month_untracked_income(year_month: str):
    df = load_all_transactions()
    projected = budget_sheets.fetch_projected_values(year_month)
    month_json = aggregate_month_json(df, year_month, sections=_all_sections(), projected=projected)
    breakdown = untracked_income.breakdown_for_month(_savings_line_items(month_json), year_month)
    return {"total": round(sum(breakdown.values()), 2), "breakdown": breakdown}


@app.get("/api/range/{range_key}/{end_year_month}/untracked-income")
def get_range_untracked_income(range_key: str, end_year_month: str):
    df, year_months = _resolve_range(range_key, end_year_month)
    # Resolved per-month (not against the range's already-summed totals) so
    # a rule scoped to only part of the range is honored correctly for the
    # months it actually covers — see untracked_income.py.
    combined: dict[str, float] = {}
    for ym in year_months:
        projected = budget_sheets.fetch_projected_values(ym)
        month_json = aggregate_month_json(df, ym, sections=_all_sections(), projected=projected)
        for label, amount in untracked_income.breakdown_for_month(_savings_line_items(month_json), ym).items():
            combined[label] = round(combined.get(label, 0.0) + amount, 2)
    return {"total": round(sum(combined.values()), 2), "breakdown": combined}


def _known_savings_line_items() -> list[str]:
    """Every Savings line item label eligible to be marked as untracked
    income: every static Savings line item, union any custom savings
    category (see custom_categories.py)."""
    labels = [li.label for s in BUDGET_SECTIONS if s.key == "savings" for li in s.line_items]
    for section, line_item in custom_categories.list_custom_categories().values():
        if section == "savings" and line_item not in labels:
            labels.append(line_item)
    return labels


@app.get("/api/untracked-income-labels")
def get_untracked_income_labels(year_month: str):
    """Every eligible Savings label, its resolved status for `year_month`,
    and that month's own dollar amount (0 if none) — the settings UI's
    source of truth for what to show a toggle for and what state to show it
    in (2026-08-02, user-requested: add/remove/change which line items
    count, scoped to the current month, current-and-future, or all)."""
    df = load_all_transactions()
    projected = budget_sheets.fetch_projected_values(year_month)
    month_json = aggregate_month_json(df, year_month, sections=_all_sections(), projected=projected)
    amounts = {li["label"]: li["actual"] for li in _savings_line_items(month_json) if li["actual"] > 0}
    return [
        {
            "label": label,
            "is_untracked": untracked_income.is_untracked_income(label, year_month),
            "amount": amounts.get(label, 0.0),
        }
        for label in _known_savings_line_items()
    ]


@app.get("/api/untracked-income-rules")
def get_untracked_income_rules():
    return untracked_income.list_rules()


class UntrackedIncomeRuleCreate(BaseModel):
    label: str
    enabled: bool
    scope: str  # "current" | "current_and_future" | "all" — see untracked_income.py
    year_month: str


@app.post("/api/untracked-income-rules")
def create_untracked_income_rule(body: UntrackedIncomeRuleCreate):
    try:
        rule = untracked_income.add_rule(body.label, body.enabled, body.scope, body.year_month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rule


@app.delete("/api/untracked-income-rules/{rule_id}")
def delete_untracked_income_rule(rule_id: str):
    removed = untracked_income.remove_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"rule {rule_id!r} not found")
    return {"removed": rule_id}


def _known_expense_line_items() -> list[tuple[str, str]]:
    """Every (section, label) the Budget Classification settings UI should
    list: every static expense line item (plus each section's "Other" row),
    union any custom expense category (see custom_categories.py) — income/
    savings line items are never part of a Need/Want split, so they're
    excluded here (see budget_rules.compute_buckets)."""
    keys: list[tuple[str, str]] = []
    for s in BUDGET_SECTIONS:
        if s.kind != "expense":
            continue
        for li in s.line_items:
            keys.append((s.key, li.label))
        if s.other_row is not None:
            keys.append((s.key, "Other"))
    for section, line_item in custom_categories.list_custom_categories().values():
        if section not in ("income", "savings") and (section, line_item) not in keys:
            keys.append((section, line_item))
    return keys


@app.get("/api/budget-classification")
def get_budget_classification():
    keys = _known_expense_line_items()
    classifications = budget_classification.all_classifications(keys)
    return [
        {"section": section, "label": label, **classifications[(section, label)]}
        for section, label in keys
    ]


class BudgetClassificationUpdate(BaseModel):
    section: str
    label: str
    budget_type: str  # "need" | "want"
    housing: bool = False
    debt: bool = False


@app.post("/api/budget-classification")
def set_budget_classification(body: BudgetClassificationUpdate):
    if body.budget_type not in ("need", "want"):
        raise HTTPException(status_code=400, detail=f"invalid budget_type: {body.budget_type!r}")
    entry = custom_budget_classification.set_override(body.section, body.label, body.budget_type, body.housing, body.debt)
    return {"section": body.section, "label": body.label, **entry}


@app.get("/api/needs-review")
def get_needs_review(year_month: str | None = None):
    df = load_all_transactions()
    year_months = [year_month] if year_month else sorted(df["year_month"].dropna().unique().tolist())
    flattened = []
    for ym in year_months:
        month_json = aggregate_month_json(df, ym, sections=_all_sections(), projected=None)
        for bucket in month_json["needs_review"]:
            for txn in bucket["transactions"]:
                flattened.append({**txn, "needs_review_category": bucket["category"], "year_month": ym})
    return {"transactions": flattened, "count": len(flattened)}


def _all_categories() -> dict[str, tuple[str, str]]:
    """CATEGORY_TO_LINE_ITEM (static, hardcoded) merged with
    custom_categories.py's runtime-persisted additions — the latter wins on
    key collision, though create_category() below already rejects
    collisions up front."""
    return {**CATEGORY_TO_LINE_ITEM, **custom_categories.list_custom_categories()}


@app.get("/api/categories")
def get_categories():
    return [
        {"category": category, "section": section, "line_item": line_item}
        for category, (section, line_item) in sorted(_all_categories().items())
    ]


def _derive_category_key(line_item: str) -> str:
    """Uppercase, space-joined key from a free-typed subcategory/line-item
    name, matching the house style of existing CATEGORY_TO_LINE_ITEM keys
    (e.g. "Mortgage (12 Warren)" -> "MORTGAGE WARREN"): digits and
    punctuation dropped entirely, common filler words dropped, remaining
    words uppercased."""
    stopwords = {"the", "a", "an", "of", "for", "in", "on", "and", "or", "to", "with"}
    words = [w.upper() for w in re.findall(r"[A-Za-z]+", line_item) if w.lower() not in stopwords]
    return " ".join(words)


class NewCategory(BaseModel):
    section: str
    line_item: str


@app.post("/api/categories")
def create_category(body: NewCategory):
    section = body.section.strip()
    line_item = body.line_item.strip()
    if not section:
        raise HTTPException(status_code=400, detail="section is required")
    if not line_item:
        raise HTTPException(status_code=400, detail="line_item (subcategory name) is required")
    if section not in {s.key for s in BUDGET_SECTIONS} and section not in custom_sections.list_custom_sections():
        raise HTTPException(status_code=400, detail=f"unknown section {section!r}")

    category = _derive_category_key(line_item)
    if not category:
        raise HTTPException(status_code=400, detail=f"couldn't derive a category key from {line_item!r} — try adding a letter")

    existing = _all_categories()
    if category in existing:
        existing_section, existing_line_item = existing[category]
        raise HTTPException(
            status_code=409,
            detail=f"category {category!r} already exists ({existing_section} → {existing_line_item})",
        )

    custom_categories.add_custom_category(category, section, line_item)
    return {"category": category, "section": section, "line_item": line_item}


@app.get("/api/sections")
def get_sections():
    static = [{"key": s.key, "label": s.label} for s in BUDGET_SECTIONS]
    custom = [{"key": key, "label": label} for key, label in custom_sections.list_custom_sections().items()]
    return static + custom


class NewSection(BaseModel):
    label: str


@app.post("/api/sections")
def create_section(body: NewSection):
    """A brand-new top-level section (Home, Daily Living, ... are the
    static ones) — distinct from POST /api/categories, which only adds a
    subcategory WITHIN an existing section (2026-08-02, user-requested:
    "I want to be able to create new sections, not just sub-sections")."""
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label is required")

    key = _derive_category_key(label)
    if not key:
        raise HTTPException(status_code=400, detail=f"couldn't derive a section key from {label!r} — try adding a letter")

    existing_keys = {s.key for s in BUDGET_SECTIONS} | set(custom_sections.list_custom_sections())
    if key in existing_keys:
        raise HTTPException(status_code=409, detail=f"section {key!r} already exists")

    custom_sections.add_custom_section(key, label)
    return {"key": key, "label": label}


class TransactionCategoryUpdate(BaseModel):
    category: str
    # User-entered free text — currently only meaningful when category is
    # "IGNORED" (the dashboard's "Ignore this transaction" action), but
    # stored on any override (2026-08-02, user-specified: ignoring a
    # transaction should let you record why).
    note: str | None = None


def _account_id_for_transaction(transaction_id: str) -> tuple[str, str] | None:
    """Scan the categorized CSVs for a transaction_id, returning
    (account_id, institution_name) if found. Small, fixed dataset (a
    handful of files) — a full scan is cheap and avoids needing a separate
    transaction_id -> account index."""
    import pandas as pd

    items = plaid_client.load_items()
    account_to_institution = {
        account["account_id"]: item["institution_name"]
        for item in items.values()
        for account in item["accounts"]
    }
    for path in glob.glob("data/plaid/*_categorized.csv"):
        account_id = Path(path).stem.removesuffix("_categorized")
        df = pd.read_csv(path)
        if (df["transaction_id"] == transaction_id).any():
            return account_id, account_to_institution.get(account_id, "")
    return None


@app.post("/api/transactions/{transaction_id}/category")
def set_transaction_category(transaction_id: str, body: TransactionCategoryUpdate):
    import categorize
    from analyze_pdf import resolve_model  # lazy: avoid pulling in Docling/langchain at server startup
    import plaid_sync

    category = categorize.normalize_category(body.category.strip().upper())
    overrides.add_transaction_override(transaction_id, category, body.note)

    located = _account_id_for_transaction(transaction_id)
    if located is None:
        raise HTTPException(status_code=404, detail=f"transaction_id {transaction_id!r} not found in any account's categorized CSV")
    account_id, institution_name = located

    # Any transaction eligible for an override already has a resolved
    # category, and the override itself short-circuits before any LLM call —
    # so this rewrite touches zero live model calls in the common case.
    plaid_sync.write_categorized_csv(resolve_model(), account_id, institution_name)

    return {"transaction_id": transaction_id, "category": category}


class IgnoreNoteUpdate(BaseModel):
    note: str | None = None


@app.post("/api/transactions/{transaction_id}/ignore-note")
def update_ignore_note(transaction_id: str, body: IgnoreNoteUpdate):
    """Edits the note on an already-ignored transaction without touching its
    category — unlike set_transaction_category above, this never needs a
    plaid_sync resync (the categorized CSVs don't store notes at all, see
    overrides.list_ignored_transactions), so it's instant."""
    updated = overrides.update_ignored_note(transaction_id, body.note)
    if not updated:
        raise HTTPException(status_code=404, detail=f"transaction_id {transaction_id!r} is not currently ignored")
    return {"transaction_id": transaction_id, "note": body.note}


class CategoryRuleCreate(BaseModel):
    pattern: str
    category: str
    match_type: str = "substring"
    # Optional — additionally requires the transaction's own amount to match
    # (within a cent) before this rule applies. For a merchant whose
    # description alone is too generic to categorize (recurring peer-to-peer
    # payments like Venmo, where the description is just "Venmo" regardless
    # of who's being paid for what), but a specific recurring dollar amount
    # does identify a specific real bill (2026-08-02, user-specified).
    amount: float | None = None


@app.get("/api/category-rules")
def get_category_rules():
    return overrides.list_merchant_rules()


@app.post("/api/category-rules")
def create_category_rule(body: CategoryRuleCreate):
    import categorize
    from analyze_pdf import resolve_model
    import plaid_sync

    category = categorize.normalize_category(body.category.strip().upper())
    try:
        rule = overrides.add_merchant_rule(body.pattern, category, body.match_type, body.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model = resolve_model()
    items = plaid_client.load_items()
    for item in items.values():
        for account in item["accounts"]:
            plaid_sync.write_categorized_csv(model, account["account_id"], item["institution_name"])

    df = load_all_transactions()
    pattern_matches = df["description"].str.contains(body.pattern, case=False, regex=(body.match_type == "regex"), na=False)
    if body.amount is not None:
        # Same tolerance as overrides._amount_matches — keep this preview
        # count consistent with what will actually get recategorized.
        pattern_matches &= (df["amount"] - body.amount).abs() < 0.01
    affected_ids = df.loc[pattern_matches, "transaction_id"].dropna().tolist()

    return {"rule": rule, "affected_transaction_count": len(affected_ids), "affected_transaction_ids": affected_ids}


@app.delete("/api/category-rules/{rule_id}")
def delete_category_rule(rule_id: str):
    removed = overrides.remove_merchant_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"rule {rule_id!r} not found")
    return {"removed": rule_id}


@app.get("/api/retirement/settings")
def get_retirement_settings():
    return retirement_settings.get_settings()


@app.post("/api/retirement/settings")
def update_retirement_settings(patch: dict):
    try:
        return retirement_settings.update_settings(patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/retirement/models")
def get_retirement_models():
    """Every model in retirement_engine.MODELS, computed against the
    current retirement_settings.py plan (2026-08-02, user-specified: the
    Retirement Planning tab's full 7-category, ~26-model spec)."""
    return {"settings": retirement_settings.get_settings(), "models": retirement_engine.compute_all(retirement_settings.get_settings())}


# Static frontend mount MUST come after every /api/* route above — a
# catch-all mounted first would shadow them.
_dist_dir = "frontend_react/dist"
if os.path.isdir(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="frontend")
