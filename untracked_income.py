"""
untracked_income.py — configurable, date-scoped overrides for which Savings
line items count as "Untracked Income" in the Sankey diagram's balance
check (see budget_sankeymatic.py) and the Budget Rules tab's 50/30/20-style
calculations (budget_rules.py): money that was never part of tracked
take-home income (true pre-tax payroll deductions, or split directly out of
the paycheck before a tracked deposit ever happens), so it needs a matching
synthetic inflow or every such month reads as overspending that isn't real.

Previously a single hardcoded set (DEFAULT_UNTRACKED_INCOME_LABELS below)
applying identically to every month, forever. This module lets the user
add/remove/change which Savings line items count, each scoped to one of:
  - "current": just the specified month (a one-off correction)
  - "current_and_future": that month onward — past months keep resolving
    however they already did (their own most-recent covering rule, or the
    static default)
  - "all": every month, past and future — retroactively rewrites the
    default, including months already synced

Resolution for a given (label, year_month): among rules for that label
whose [start_month, end_month] range covers year_month, the most recently
created one wins (last-write-wins, same convention as overrides.py's
transaction_overrides). If no rule matches at all, falls back to
DEFAULT_UNTRACKED_INCOME_LABELS — today's hardcoded behavior, unchanged for
anyone who hasn't customized anything (2026-08-02, user-requested).

Deliberately no in-memory cache — same rationale as overrides.py: the
writer (API server) and reader (plaid_sync.py / the dashboard's own
request) aren't guaranteed to be the same process, so a load-once cache
would go stale the moment a rule is added elsewhere.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

UNTRACKED_INCOME_FILE = Path("untracked_income_overrides.json")

VALID_SCOPES = ("current", "current_and_future", "all")

# The original hardcoded set (see budget_sankeymatic.py's prior
# UNTRACKED_INCOME_LABELS) — now just the fallback when no rule exists for
# a given (label, year_month) at all.
DEFAULT_UNTRACKED_INCOME_LABELS = {
    "Retirement (401k + Match)", "Retirement (MTRS)",
    "Emergency Fund", "Managed Brokerages",
}


def _load() -> list[dict]:
    if not UNTRACKED_INCOME_FILE.exists():
        return []
    with open(UNTRACKED_INCOME_FILE) as f:
        return json.load(f)


def _save(rules: list[dict]) -> None:
    with open(UNTRACKED_INCOME_FILE, "w") as f:
        json.dump(rules, f, indent=2)


def add_rule(label: str, enabled: bool, scope: str, year_month: str) -> dict:
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope!r}; must be one of {VALID_SCOPES}")
    if scope == "current":
        start_month, end_month = year_month, year_month
    elif scope == "current_and_future":
        start_month, end_month = year_month, None
    else:  # "all"
        start_month, end_month = None, None

    rule = {
        "id": f"ui_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}",
        "label": label,
        "enabled": enabled,
        "scope": scope,
        "start_month": start_month,
        "end_month": end_month,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    rules = _load()
    rules.append(rule)
    _save(rules)
    return rule


def list_rules() -> list[dict]:
    return _load()


def remove_rule(rule_id: str) -> bool:
    rules = _load()
    before = len(rules)
    rules = [r for r in rules if r["id"] != rule_id]
    if len(rules) == before:
        return False
    _save(rules)
    return True


def _rule_covers(rule: dict, year_month: str) -> bool:
    if rule["start_month"] is not None and year_month < rule["start_month"]:
        return False
    if rule["end_month"] is not None and year_month > rule["end_month"]:
        return False
    return True


def is_untracked_income(label: str, year_month: str | None) -> bool:
    """Resolves whether `label` counts as untracked income for `year_month`.
    year_month may be None (e.g. an empty/malformed month_json) — falls
    straight through to the static default in that case, since there's no
    month to resolve a rule against."""
    if year_month is None:
        return label in DEFAULT_UNTRACKED_INCOME_LABELS
    matching = [r for r in _load() if r["label"] == label]
    matching.sort(key=lambda r: r["created_at"], reverse=True)
    for rule in matching:
        if _rule_covers(rule, year_month):
            return rule["enabled"]
    return label in DEFAULT_UNTRACKED_INCOME_LABELS


def breakdown_for_month(savings_line_items: list[dict], year_month: str) -> dict[str, float]:
    """{label: amount} for every positive-actual Savings line item
    (LineItem-shaped dicts, e.g. from aggregate_month_json's "savings"
    section) currently resolved as untracked income for this specific
    year_month — the numbers behind the diagram's "Untracked Income" node,
    surfaced for the explanation modal's breakdown (2026-08-02,
    user-requested: "a breakdown to explain the number")."""
    return {
        li["label"]: round(li["actual"], 2)
        for li in savings_line_items
        if li["actual"] > 0 and is_untracked_income(li["label"], year_month)
    }
