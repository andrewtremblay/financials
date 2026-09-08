"""
overrides.py — manual category overrides, checked before classify_boilerplate
and the LLM in categorize.py's categorize_with_prompt.

Two kinds, both keyed on the transaction description (never touching
memo.py's LLM cache):

- transaction_overrides: a single transaction_id -> {category, note, set_at}.
  For "this one charge should be X." `note` is user-entered free text,
  currently only used when category is IGNORED_CATEGORY (the dashboard's
  "Ignore this transaction" action — see budget_aggregate.py's Ignored
  section handling), but stored generically on every override.
- merchant_rules: an ordered list of {pattern, match_type, category,
  amount?}. For "always categorize this merchant as X going forward." First
  match wins, same convention as categorize.BOILERPLATE_CATEGORY_PATTERNS.
  `amount`, if set, additionally requires the transaction's own amount to
  match (within a cent) — for a merchant whose description is too generic
  to categorize on its own (recurring peer-to-peer payments like Venmo/
  Zelle/PayPal, where the description is just "Venmo" regardless of who's
  getting paid for what) but a specific recurring amount identifies a
  specific real-world bill (2026-08-02, user-specified: a recurring $120
  Venmo payment that should always mean "Home -> Professional Cleaning",
  without dragging every OTHER Venmo payment along with it).

Deliberately no in-memory cache: the writer (the API server process) and the
reader (the daily plaid_sync.py launchd job, a separate process) are not the
same process, so a load-once cache would go stale the moment the API writes
a new override. Read fresh from disk on every lookup — this file is tiny
(a personal budget's worth of corrections), so the I/O cost is negligible.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sheet_category_map import IGNORED_CATEGORY

OVERRIDES_FILE = Path("category_overrides.json")


def _load() -> dict:
    if not OVERRIDES_FILE.exists():
        return {"transaction_overrides": {}, "merchant_rules": []}
    with open(OVERRIDES_FILE) as f:
        data = json.load(f)
    data.setdefault("transaction_overrides", {})
    data.setdefault("merchant_rules", [])
    return data


def _save(data: dict) -> None:
    with open(OVERRIDES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _matches(pattern: str, match_type: str, description: str) -> bool:
    if match_type == "exact":
        return pattern.strip().lower() == description.strip().lower()
    if match_type == "regex":
        return re.search(pattern, description, re.I) is not None
    # "substring" (default)
    return re.search(re.escape(pattern), description, re.I) is not None


def _amount_matches(rule_amount: float | None, amount: float | None) -> bool:
    if rule_amount is None:
        return True  # rule has no amount constraint
    if amount is None:
        return False  # rule requires a specific amount; this transaction has none to compare
    return abs(rule_amount - amount) < 0.01


def lookup_transaction_override(transaction_id: str | None) -> str | None:
    if not transaction_id:
        return None
    entry = _load()["transaction_overrides"].get(transaction_id)
    return entry["category"] if entry else None


def lookup_merchant_rule(description: str, amount: float | None = None) -> str | None:
    for rule in _load()["merchant_rules"]:
        if _matches(rule["pattern"], rule["match_type"], description) and _amount_matches(rule.get("amount"), amount):
            return rule["category"]
    return None


def add_transaction_override(transaction_id: str, category: str, note: str | None = None) -> dict:
    data = _load()
    entry = {"category": category, "set_at": datetime.now(timezone.utc).isoformat(), "note": note}
    data["transaction_overrides"][transaction_id] = entry
    _save(data)
    return entry


def list_ignored_transactions() -> dict[str, dict]:
    """transaction_id -> {note, set_at} for every override whose category is
    IGNORED_CATEGORY — used to enrich the dashboard's Ignored section with
    each transaction's reason. Notes live only here, never in the
    categorized CSVs, so editing one (update_ignored_note below) needs no
    plaid_sync resync."""
    return {
        tx_id: {"note": entry.get("note"), "set_at": entry["set_at"]}
        for tx_id, entry in _load()["transaction_overrides"].items()
        if entry["category"] == IGNORED_CATEGORY
    }


def update_ignored_note(transaction_id: str, note: str | None) -> bool:
    """Update just the note on an existing IGNORED override. Returns False
    (caller should 404) if the transaction isn't currently ignored — editing
    a note only makes sense for a transaction already in that state."""
    data = _load()
    entry = data["transaction_overrides"].get(transaction_id)
    if entry is None or entry["category"] != IGNORED_CATEGORY:
        return False
    entry["note"] = note
    _save(data)
    return True


def add_merchant_rule(pattern: str, category: str, match_type: str = "substring", amount: float | None = None) -> dict:
    if match_type not in ("substring", "exact", "regex"):
        raise ValueError(f"invalid match_type: {match_type}")
    data = _load()
    rule = {
        "id": f"r_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}",
        "match_type": match_type,
        "pattern": pattern,
        "category": category,
        "amount": amount,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["merchant_rules"].append(rule)
    _save(data)
    return rule


def list_merchant_rules() -> list[dict]:
    return _load()["merchant_rules"]


def remove_merchant_rule(rule_id: str) -> bool:
    data = _load()
    before = len(data["merchant_rules"])
    data["merchant_rules"] = [r for r in data["merchant_rules"] if r["id"] != rule_id]
    if len(data["merchant_rules"]) == before:
        return False
    _save(data)
    return True
