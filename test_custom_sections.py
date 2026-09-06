"""
Tests for custom_sections.py.

Run with: uv run pytest test_custom_sections.py -v
"""
import pytest

import custom_sections


@pytest.fixture(autouse=True)
def isolated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_sections, "CUSTOM_SECTIONS_FILE", tmp_path / "custom_sections.json")


def test_empty_by_default():
    assert custom_sections.list_custom_sections() == {}


def test_add_then_list():
    custom_sections.add_custom_section("BUSINESS", "Business Expenses")
    assert custom_sections.list_custom_sections() == {"BUSINESS": "Business Expenses"}


def test_add_multiple_sections():
    custom_sections.add_custom_section("BUSINESS", "Business Expenses")
    custom_sections.add_custom_section("HOBBIES", "Hobbies")
    assert custom_sections.list_custom_sections() == {"BUSINESS": "Business Expenses", "HOBBIES": "Hobbies"}


def test_add_overwrites_existing_key():
    custom_sections.add_custom_section("BUSINESS", "Business Expenses")
    custom_sections.add_custom_section("BUSINESS", "Business Costs")
    assert custom_sections.list_custom_sections() == {"BUSINESS": "Business Costs"}


def test_survives_reload(tmp_path, monkeypatch):
    custom_sections.add_custom_section("BUSINESS", "Business Expenses")
    store_path = custom_sections.CUSTOM_SECTIONS_FILE
    import importlib
    importlib.reload(custom_sections)
    monkeypatch.setattr(custom_sections, "CUSTOM_SECTIONS_FILE", store_path)
    assert custom_sections.list_custom_sections() == {"BUSINESS": "Business Expenses"}
