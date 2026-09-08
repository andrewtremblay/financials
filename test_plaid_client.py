"""
Tests for plaid_client.py.

Run with: uv run pytest test_plaid_client.py -v
"""
import pytest

from plaid.api.plaid_api import PlaidApi

from plaid_client import get_plaid_client, load_items, save_items


# ---------------------------------------------------------------------------
# load_items / save_items
# ---------------------------------------------------------------------------

class TestItemsRoundTrip:
    def test_load_items_missing_file_returns_empty_dict(self, tmp_path):
        assert load_items(tmp_path / "does_not_exist.json") == {}

    def test_save_then_load_round_trip(self, tmp_path):
        items_file = tmp_path / "plaid_items.json"
        items = {
            "item-1": {
                "item_id": "item-1",
                "access_token": "access-sandbox-xyz",
                "institution_name": "Charles Schwab",
                "accounts": [{"account_id": "acct-1", "name": "Checking", "mask": "1234", "subtype": "checking"}],
                "cursor": None,
            }
        }
        save_items(items, items_file)
        assert load_items(items_file) == items

    def test_save_overwrites_existing_file(self, tmp_path):
        items_file = tmp_path / "plaid_items.json"
        save_items({"a": {"item_id": "a"}}, items_file)
        save_items({"b": {"item_id": "b"}}, items_file)
        assert load_items(items_file) == {"b": {"item_id": "b"}}


# ---------------------------------------------------------------------------
# get_plaid_client
# ---------------------------------------------------------------------------

class TestGetPlaidClient:
    def test_raises_without_client_id(self, monkeypatch):
        monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
        monkeypatch.setenv("PLAID_SECRET", "secret")
        with pytest.raises(SystemExit):
            get_plaid_client()

    def test_raises_without_secret(self, monkeypatch):
        monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
        monkeypatch.delenv("PLAID_SECRET", raising=False)
        with pytest.raises(SystemExit):
            get_plaid_client()

    def test_raises_on_unknown_environment(self, monkeypatch):
        monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
        monkeypatch.setenv("PLAID_SECRET", "secret")
        monkeypatch.setenv("PLAID_ENV", "staging")
        with pytest.raises(SystemExit):
            get_plaid_client()

    def test_builds_client_with_valid_sandbox_credentials(self, monkeypatch):
        monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
        monkeypatch.setenv("PLAID_SECRET", "secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")
        client = get_plaid_client()
        assert isinstance(client, PlaidApi)

    def test_defaults_to_sandbox_when_env_unset(self, monkeypatch):
        monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
        monkeypatch.setenv("PLAID_SECRET", "secret")
        monkeypatch.delenv("PLAID_ENV", raising=False)
        client = get_plaid_client()
        assert isinstance(client, PlaidApi)
