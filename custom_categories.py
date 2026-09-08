"""
custom_categories.py — user-added category -> (section, line_item) mappings,
created via the recategorize UI's "add a new category" flow (see
RecategorizeModal.tsx and POST /api/categories in api_server.py).

sheet_category_map.CATEGORY_TO_LINE_ITEM is a hardcoded Python dict — a
category typed through the UI is never added to it, so GET /api/categories
(which just sorts and returns that dict) could never know about it and the
recategorize dropdown would never show it again. This module is the durable,
runtime-writable complement: GET /api/categories merges
CATEGORY_TO_LINE_ITEM with this store's contents every time it's computed,
so newly-added categories persist across server restarts.

Same file-per-write, no-in-memory-cache pattern as overrides.py (see that
module's docstring for why) and the same gitignore treatment — see
.gitignore.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

CUSTOM_CATEGORIES_FILE = Path("custom_categories.json")


def _load() -> dict:
    if not CUSTOM_CATEGORIES_FILE.exists():
        return {}
    with open(CUSTOM_CATEGORIES_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(CUSTOM_CATEGORIES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def list_custom_categories() -> dict[str, tuple[str, str]]:
    """{category: (section, line_item)} — same shape as
    sheet_category_map.CATEGORY_TO_LINE_ITEM, so callers can merge the two
    with a single dict spread."""
    return {category: (entry["section"], entry["line_item"]) for category, entry in _load().items()}


def add_custom_category(category: str, section: str, line_item: str) -> dict:
    data = _load()
    entry = {
        "section": section,
        "line_item": line_item,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data[category] = entry
    _save(data)
    return entry
