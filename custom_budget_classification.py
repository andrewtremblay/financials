"""
custom_budget_classification.py — user overrides for each line item's
Need/Want/Debt/Housing tagging, used by budget_rules.py to compute the
50/30/20, 28/36, 70/20/10, and 80/20 rules.

budget_classification.LINE_ITEM_BUDGET_TYPE is a hardcoded best-guess
default per line item ("Groceries" is a Need, "Streaming / Movies" is a
Want, ...) — genuinely subjective per household, so this module is the
durable, runtime-writable override layer on top of it. Same file-per-write,
no-in-memory-cache, gitignored pattern as custom_categories.py/overrides.py
(2026-08-02, user-specified: best-guess defaults with the ability to
override, rather than a blank slate that needs everything tagged by hand
before any rule shows useful output).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

CUSTOM_BUDGET_CLASSIFICATION_FILE = Path("custom_budget_classification.json")


def _load() -> dict:
    if not CUSTOM_BUDGET_CLASSIFICATION_FILE.exists():
        return {}
    with open(CUSTOM_BUDGET_CLASSIFICATION_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(CUSTOM_BUDGET_CLASSIFICATION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _key(section: str, label: str) -> str:
    # A single string key (not nested dicts) keeps _load/_save/list flat and
    # trivial to merge with budget_classification.py's static dict, which is
    # keyed the same way.
    return f"{section}␟{label}"


def list_overrides() -> dict[tuple[str, str], dict]:
    """{(section, label): {budget_type, housing, debt}} for every line item
    with a user override."""
    result = {}
    for key, entry in _load().items():
        section, label = key.split("␟", 1)
        result[(section, label)] = {
            "budget_type": entry["budget_type"],
            "housing": entry["housing"],
            "debt": entry["debt"],
        }
    return result


def set_override(section: str, label: str, budget_type: str, housing: bool, debt: bool) -> dict:
    if budget_type not in ("need", "want"):
        raise ValueError(f"invalid budget_type: {budget_type!r}")
    data = _load()
    entry = {
        "budget_type": budget_type,
        "housing": housing,
        "debt": debt,
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    data[_key(section, label)] = entry
    _save(data)
    return entry
