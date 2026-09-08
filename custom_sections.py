"""
custom_sections.py — user-added TOP-LEVEL budget sections, created via the
"add a new section" flow in the recategorize UI (RecategorizeModal.tsx).

Distinct from custom_categories.py, which adds a subcategory WITHIN an
existing section — this is for when none of the existing sections (Home,
Daily Living, Transportation, ...) fit at all (2026-08-02, user-requested:
"I want to be able to create new sections, not just sub-sections").

A custom section always starts with zero static line items — every
category assigned to it resolves via budget_aggregate.aggregate_month_json's
existing stray-key synthesis (the same mechanism that already handles a
custom category with no schema row), so nothing downstream needs to treat
a custom section specially once api_server.py merges it into the sections
list it passes to aggregate_month_json/aggregate_range_json.

Same file-per-write, no-in-memory-cache, gitignored pattern as
custom_categories.py.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

CUSTOM_SECTIONS_FILE = Path("custom_sections.json")


def _load() -> dict:
    if not CUSTOM_SECTIONS_FILE.exists():
        return {}
    with open(CUSTOM_SECTIONS_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(CUSTOM_SECTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def list_custom_sections() -> dict[str, str]:
    """{section_key: label} for every custom section."""
    return {key: entry["label"] for key, entry in _load().items()}


def add_custom_section(key: str, label: str) -> dict:
    data = _load()
    entry = {"label": label, "created_at": datetime.now(timezone.utc).isoformat()}
    data[key] = entry
    _save(data)
    return entry
