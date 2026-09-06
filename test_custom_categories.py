"""
Tests for custom_categories.py.

Run with: uv run pytest test_custom_categories.py -v
"""
import importlib

import pytest

import custom_categories


@pytest.fixture(autouse=True)
def isolated_custom_categories_file(tmp_path, monkeypatch):
    """Every test gets its own store file — never touch the real one."""
    monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")


class TestCustomCategories:
    def test_no_file_returns_empty(self):
        assert custom_categories.list_custom_categories() == {}

    def test_add_then_list(self):
        custom_categories.add_custom_category("CONCERT TICKETS", "ENTERTAINMENT", "Concert Tickets")
        assert custom_categories.list_custom_categories() == {
            "CONCERT TICKETS": ("ENTERTAINMENT", "Concert Tickets"),
        }

    def test_add_multiple(self):
        custom_categories.add_custom_category("CONCERT TICKETS", "ENTERTAINMENT", "Concert Tickets")
        custom_categories.add_custom_category("PET CARE", "DAILY LIVING", "Pet Care")
        result = custom_categories.list_custom_categories()
        assert result["CONCERT TICKETS"] == ("ENTERTAINMENT", "Concert Tickets")
        assert result["PET CARE"] == ("DAILY LIVING", "Pet Care")

    def test_overwrite_existing_key(self):
        custom_categories.add_custom_category("PET CARE", "DAILY LIVING", "Pet Care")
        custom_categories.add_custom_category("PET CARE", "HEALTH", "Vet Bills")
        assert custom_categories.list_custom_categories()["PET CARE"] == ("HEALTH", "Vet Bills")

    def test_add_returns_entry_with_timestamp(self):
        entry = custom_categories.add_custom_category("PET CARE", "DAILY LIVING", "Pet Care")
        assert entry["section"] == "DAILY LIVING"
        assert entry["line_item"] == "Pet Care"
        assert "created_at" in entry

    def test_no_in_memory_cache_across_reload(self, tmp_path, monkeypatch):
        """Same rationale as overrides.py's equivalent test: the writer (API
        process) and reader (a separate process reading the same store)
        must never see stale in-memory state — always read fresh from
        disk."""
        custom_categories.add_custom_category("PET CARE", "DAILY LIVING", "Pet Care")
        importlib.reload(custom_categories)
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")
        assert custom_categories.list_custom_categories() == {
            "PET CARE": ("DAILY LIVING", "Pet Care"),
        }
