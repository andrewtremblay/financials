"""
plaid_client.py — Shared Plaid API client + local item storage.

Items (linked accounts) are stored in plaid_items.json, keyed by item_id.
This file contains access tokens and is gitignored.
"""

import json
import os
from pathlib import Path

import plaid
from plaid.api import plaid_api

PLAID_ITEMS_FILE = Path("plaid_items.json")

_ENVIRONMENTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def get_plaid_client() -> plaid_api.PlaidApi:
    """
    Build a Plaid API client from PLAID_CLIENT_ID / PLAID_SECRET / PLAID_ENV env vars.
    Raises SystemExit with a clear message if credentials are missing.
    """
    client_id = os.getenv("PLAID_CLIENT_ID")
    secret = os.getenv("PLAID_SECRET")
    env_name = os.getenv("PLAID_ENV", "sandbox").lower()

    if not client_id or not secret:
        raise SystemExit(
            "Missing Plaid credentials. Set PLAID_CLIENT_ID and PLAID_SECRET in .env "
            "(get them from https://dashboard.plaid.com/team/keys)."
        )
    if env_name not in _ENVIRONMENTS:
        raise SystemExit(
            f"Unknown PLAID_ENV {env_name!r}. Use 'sandbox' or 'production'."
        )

    configuration = plaid.Configuration(
        host=_ENVIRONMENTS[env_name],
        api_key={"clientId": client_id, "secret": secret},
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def load_items(items_file: Path = PLAID_ITEMS_FILE) -> dict:
    """Load linked Plaid items, keyed by item_id. Returns {} if no file exists yet."""
    if not items_file.exists():
        return {}
    with open(items_file, "r") as f:
        return json.load(f)


def save_items(items: dict, items_file: Path = PLAID_ITEMS_FILE) -> None:
    """Persist linked Plaid items to disk."""
    with open(items_file, "w") as f:
        json.dump(items, f, indent=2)
