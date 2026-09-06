"""
Tests for api_server.py's category endpoints — GET/POST /api/categories and
GET /api/sections. These back the RecategorizeModal "add a new category"
flow: sheet_category_map.CATEGORY_TO_LINE_ITEM is a hardcoded dict, so a
category typed through the UI used to never show up in the dropdown again —
custom_categories.py + these endpoints are the fix. See CLAUDE.md/the task
that introduced this file for the full writeup.

Run with: uv run pytest test_api_server.py -v
"""
import importlib

import pytest
from fastapi.testclient import TestClient

import api_server
import custom_budget_classification
import custom_categories
import custom_sections
import overrides
import retirement_settings
import untracked_income


@pytest.fixture(autouse=True)
def isolated_custom_categories_file(tmp_path, monkeypatch):
    """Every test gets its own store file — never touch the real one."""
    monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")


@pytest.fixture(autouse=True)
def isolated_custom_sections_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_sections, "CUSTOM_SECTIONS_FILE", tmp_path / "custom_sections.json")


@pytest.fixture(autouse=True)
def isolated_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "OVERRIDES_FILE", tmp_path / "category_overrides.json")


@pytest.fixture(autouse=True)
def isolated_budget_classification_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_budget_classification, "CUSTOM_BUDGET_CLASSIFICATION_FILE", tmp_path / "custom_budget_classification.json")


@pytest.fixture(autouse=True)
def isolated_untracked_income_file(tmp_path, monkeypatch):
    monkeypatch.setattr(untracked_income, "UNTRACKED_INCOME_FILE", tmp_path / "untracked_income_overrides.json")


@pytest.fixture(autouse=True)
def isolated_retirement_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(retirement_settings, "RETIREMENT_SETTINGS_FILE", tmp_path / "retirement_settings.json")


@pytest.fixture
def client():
    return TestClient(api_server.app)


class TestGetSections:
    def test_returns_budget_schema_sections(self, client):
        resp = client.get("/api/sections")
        assert resp.status_code == 200
        keys = {s["key"] for s in resp.json()}
        assert {"income", "savings", "HOME", "ENTERTAINMENT"} <= keys

    def test_custom_section_absent_before_creation(self, client):
        resp = client.get("/api/sections")
        assert "BUSINESS" not in {s["key"] for s in resp.json()}


class TestCreateSection:
    def test_create_then_shows_up_in_get_sections(self, client):
        create_resp = client.post("/api/sections", json={"label": "Business Expenses"})
        assert create_resp.status_code == 200
        assert create_resp.json() == {"key": "BUSINESS EXPENSES", "label": "Business Expenses"}

        list_resp = client.get("/api/sections")
        entry = next(s for s in list_resp.json() if s["key"] == "BUSINESS EXPENSES")
        assert entry["label"] == "Business Expenses"

    def test_blank_label_rejected(self, client):
        resp = client.post("/api/sections", json={"label": "   "})
        assert resp.status_code == 400

    def test_label_with_no_letters_rejected(self, client):
        resp = client.post("/api/sections", json={"label": "123"})
        assert resp.status_code == 400

    def test_colliding_with_static_section_rejected(self, client):
        resp = client.post("/api/sections", json={"label": "Home"})
        assert resp.status_code == 409

    def test_colliding_with_existing_custom_section_rejected(self, client):
        client.post("/api/sections", json={"label": "Business Expenses"})
        resp = client.post("/api/sections", json={"label": "Business Expenses"})
        assert resp.status_code == 409

    def test_new_section_immediately_usable_by_create_category(self, client):
        """The whole point of a custom section: /api/categories must accept
        it as a valid `section` right away, not just list it."""
        client.post("/api/sections", json={"label": "Business Expenses"})
        resp = client.post("/api/categories", json={"section": "BUSINESS EXPENSES", "line_item": "Office Supplies"})
        assert resp.status_code == 200
        assert resp.json()["section"] == "BUSINESS EXPENSES"


class TestGetCategories:
    def test_includes_static_categories(self, client):
        resp = client.get("/api/categories")
        cats = {c["category"] for c in resp.json()}
        assert "WAGES" in cats
        assert "GROCERY" in cats

    def test_custom_category_absent_before_creation(self, client):
        resp = client.get("/api/categories")
        assert "CONCERT TICKETS" not in {c["category"] for c in resp.json()}


class TestCreateCategory:
    def test_create_then_shows_up_in_get_categories(self, client):
        """The core bug fix: a category added through the modal must appear
        in the dropdown on the very next /api/categories load, not just
        stay in whatever local component state created it."""
        create_resp = client.post("/api/categories", json={"section": "ENTERTAINMENT", "line_item": "Concert Tickets"})
        assert create_resp.status_code == 200
        body = create_resp.json()
        assert body == {"category": "CONCERT TICKETS", "section": "ENTERTAINMENT", "line_item": "Concert Tickets"}

        list_resp = client.get("/api/categories")
        entry = next(c for c in list_resp.json() if c["category"] == "CONCERT TICKETS")
        assert entry["section"] == "ENTERTAINMENT"
        assert entry["line_item"] == "Concert Tickets"

    def test_derives_house_style_key(self, client):
        """Matches sheet_category_map.py's existing "MORTGAGE WARREN" for
        "Mortgage (12 Warren)" convention: numbers/punctuation dropped,
        remaining words uppercased."""
        resp = client.post("/api/categories", json={"section": "HOME", "line_item": "Mortgage (12 Warren St)"})
        assert resp.status_code == 200
        assert resp.json()["category"] == "MORTGAGE WARREN ST"

    def test_unknown_section_rejected(self, client):
        resp = client.post("/api/categories", json={"section": "NOT_A_REAL_SECTION", "line_item": "Whatever"})
        assert resp.status_code == 400

    def test_blank_line_item_rejected(self, client):
        resp = client.post("/api/categories", json={"section": "HOME", "line_item": "   "})
        assert resp.status_code == 400

    def test_line_item_with_no_letters_rejected(self, client):
        resp = client.post("/api/categories", json={"section": "HOME", "line_item": "123"})
        assert resp.status_code == 400

    def test_colliding_with_static_category_rejected(self, client):
        resp = client.post("/api/categories", json={"section": "DAILY LIVING", "line_item": "Wages"})
        assert resp.status_code == 409

    def test_colliding_with_existing_custom_category_rejected(self, client):
        client.post("/api/categories", json={"section": "ENTERTAINMENT", "line_item": "Concert Tickets"})
        resp = client.post("/api/categories", json={"section": "HEALTH", "line_item": "Concert Tickets"})
        assert resp.status_code == 409


class TestUpdateIgnoreNote:
    """POST /api/transactions/{id}/ignore-note — the lightweight note-only
    edit for the dashboard's Ignored section (unlike POST .../category, this
    never calls plaid_sync/resolve_model, so it's fully testable here without
    mocking the Plaid/LLM pipeline)."""

    def test_updates_note_on_ignored_transaction(self, client):
        overrides.add_transaction_override("txn-1", "IGNORED", "first reason")
        resp = client.post("/api/transactions/txn-1/ignore-note", json={"note": "better reason"})
        assert resp.status_code == 200
        assert resp.json() == {"transaction_id": "txn-1", "note": "better reason"}
        assert overrides.list_ignored_transactions()["txn-1"]["note"] == "better reason"

    def test_404_when_not_ignored(self, client):
        overrides.add_transaction_override("txn-1", "GIFTS")
        resp = client.post("/api/transactions/txn-1/ignore-note", json={"note": "some note"})
        assert resp.status_code == 404

    def test_404_when_transaction_unknown(self, client):
        resp = client.post("/api/transactions/nonexistent/ignore-note", json={"note": "some note"})
        assert resp.status_code == 404


class TestBudgetClassification:
    def test_get_includes_static_defaults(self, client):
        resp = client.get("/api/budget-classification")
        assert resp.status_code == 200
        entries = {(e["section"], e["label"]): e for e in resp.json()}
        assert entries[("DAILY LIVING", "Groceries")]["budget_type"] == "need"
        assert entries[("HOME", "Mortgage (12 Warren)")]["housing"] is True

    def test_post_override_then_reflected_in_get(self, client):
        resp = client.post("/api/budget-classification", json={
            "section": "DAILY LIVING", "label": "Groceries", "budget_type": "want", "housing": False, "debt": False,
        })
        assert resp.status_code == 200
        entries = {(e["section"], e["label"]): e for e in client.get("/api/budget-classification").json()}
        assert entries[("DAILY LIVING", "Groceries")]["budget_type"] == "want"

    def test_invalid_budget_type_rejected(self, client):
        resp = client.post("/api/budget-classification", json={"section": "HOME", "label": "Other", "budget_type": "sometimes"})
        assert resp.status_code == 400


class TestUntrackedIncomeRules:
    """CRUD for untracked_income.py's rule store — GET/POST/DELETE
    /api/untracked-income-rules. The read-heavy endpoints
    (/api/months/{ym}/untracked-income, /api/untracked-income-labels) call
    load_all_transactions()/budget_sheets.fetch_projected_values, the same
    live-data dependencies that keep get_month/get_month_budget_rules out
    of this file too — covered instead by e2e Playwright verification
    against the real running server."""

    def test_empty_by_default(self, client):
        resp = client.get("/api/untracked-income-rules")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_then_list(self, client):
        resp = client.post("/api/untracked-income-rules", json={
            "label": "Other Savings", "enabled": True, "scope": "current", "year_month": "2026-07",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["label"] == "Other Savings"
        assert body["start_month"] == "2026-07"
        assert body["end_month"] == "2026-07"

        rules = client.get("/api/untracked-income-rules").json()
        assert len(rules) == 1
        assert rules[0]["id"] == body["id"]

    def test_scope_current_and_future_leaves_end_month_open(self, client):
        resp = client.post("/api/untracked-income-rules", json={
            "label": "Other Savings", "enabled": True, "scope": "current_and_future", "year_month": "2026-07",
        })
        body = resp.json()
        assert body["start_month"] == "2026-07"
        assert body["end_month"] is None

    def test_scope_all_leaves_both_open(self, client):
        resp = client.post("/api/untracked-income-rules", json={
            "label": "Other Savings", "enabled": True, "scope": "all", "year_month": "2026-07",
        })
        body = resp.json()
        assert body["start_month"] is None
        assert body["end_month"] is None

    def test_invalid_scope_rejected(self, client):
        resp = client.post("/api/untracked-income-rules", json={
            "label": "Other Savings", "enabled": True, "scope": "sometimes", "year_month": "2026-07",
        })
        assert resp.status_code == 400

    def test_delete_rule(self, client):
        created = client.post("/api/untracked-income-rules", json={
            "label": "Other Savings", "enabled": True, "scope": "all", "year_month": "2026-07",
        }).json()
        resp = client.delete(f"/api/untracked-income-rules/{created['id']}")
        assert resp.status_code == 200
        assert client.get("/api/untracked-income-rules").json() == []

    def test_delete_nonexistent_rule_404s(self, client):
        resp = client.delete("/api/untracked-income-rules/nonexistent")
        assert resp.status_code == 404


class TestPersistsAcrossFreshProcess:
    def test_survives_module_reload(self, client, monkeypatch):
        """The real regression this guards against: /api/categories used to
        be computed purely from a hardcoded Python dict (sheet_category_map.
        CATEGORY_TO_LINE_ITEM), so a category typed through the UI would
        vanish the moment the server restarted — it was never written
        anywhere durable. Simulate a restart by reloading custom_categories
        (dropping all in-memory module state, same technique as
        test_overrides.py's test_no_in_memory_cache_across_reload) and
        confirming api_server still finds it on the next request."""
        create_resp = client.post("/api/categories", json={"section": "DAILY LIVING", "line_item": "Pet Supplies"})
        assert create_resp.status_code == 200

        store_path = custom_categories.CUSTOM_CATEGORIES_FILE
        assert store_path.exists()

        importlib.reload(custom_categories)
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", store_path)

        # api_server holds a reference to the custom_categories *module*
        # (`import custom_categories`), not to any of its functions or
        # values individually, so the reload above is visible on the very
        # next request without needing to reload/recreate api_server.app.
        list_resp = client.get("/api/categories")
        entry = next(c for c in list_resp.json() if c["category"] == "PET SUPPLIES")
        assert entry["section"] == "DAILY LIVING"
        assert entry["line_item"] == "Pet Supplies"


class TestRetirementSettings:
    def test_get_returns_defaults_when_unset(self, client):
        resp = client.get("/api/retirement/settings")
        assert resp.status_code == 200
        assert resp.json() == retirement_settings.DEFAULT_SETTINGS

    def test_post_updates_and_persists(self, client):
        resp = client.post("/api/retirement/settings", json={"current_age": 40.0, "retirement_age": 62.0})
        assert resp.status_code == 200
        assert resp.json()["current_age"] == 40.0
        assert client.get("/api/retirement/settings").json()["retirement_age"] == 62.0

    def test_unknown_field_rejected(self, client):
        resp = client.post("/api/retirement/settings", json={"not_a_real_field": 1.0})
        assert resp.status_code == 400


class TestRetirementModels:
    def test_returns_settings_and_all_models(self, client):
        client.post("/api/retirement/settings", json={
            "current_age": 35.0, "retirement_age": 65.0, "life_expectancy_age": 90.0,
            "current_portfolio_balance": 200000.0, "annual_savings": 20000.0,
            "desired_annual_spending": 60000.0,
        })
        resp = client.get("/api/retirement/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["settings"]["current_age"] == 35.0
        assert len(body["models"]) >= 26
        for m in body["models"]:
            assert "error" not in m["result"], f"{m['key']} failed: {m['result']}"

    def test_works_with_default_zero_settings(self, client):
        """A brand-new install with nothing configured yet must not 500."""
        resp = client.get("/api/retirement/models")
        assert resp.status_code == 200
        assert len(resp.json()["models"]) >= 26
