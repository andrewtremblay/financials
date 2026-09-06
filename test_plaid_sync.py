"""
Tests for plaid_sync.py.

Run with: uv run pytest test_plaid_sync.py -v
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# plaid_sync.py imports categorize (which imports utils, which imports Docling
# and langchain_community for real PDF parsing). Patch those heavy deps before
# importing, same convention as test_utils.py.
for mod in [
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "docling",
    "docling.document_converter",
    "memo",
]:
    sys.modules[mod] = MagicMock()

import categorize  # noqa: E402 — real module (lightweight once its deps are mocked); tests configure .categorize per-case
import plaid_sync  # noqa: E402


def fake_transaction(account_id, transaction_id, date, name, amount, merchant_name=None, pending=False):
    return SimpleNamespace(
        account_id=account_id,
        transaction_id=transaction_id,
        date=date,
        name=name,
        merchant_name=merchant_name,
        amount=amount,
        pending=pending,
    )


def fake_removed(account_id, transaction_id):
    return SimpleNamespace(account_id=account_id, transaction_id=transaction_id)


def fake_sync_response(added=(), modified=(), removed=(), next_cursor="cursor-1", has_more=False):
    return SimpleNamespace(
        added=list(added), modified=list(modified), removed=list(removed),
        next_cursor=next_cursor, has_more=has_more,
    )


# ---------------------------------------------------------------------------
# _transaction_description
# ---------------------------------------------------------------------------

class TestTransactionDescription:
    def test_prefers_merchant_name(self):
        txn = fake_transaction("a", "t1", "2026-01-05", "RAW NAME", 10.0, merchant_name="Nice Merchant")
        assert plaid_sync._transaction_description(txn) == "Nice Merchant"

    def test_falls_back_to_name(self):
        txn = fake_transaction("a", "t1", "2026-01-05", "RAW NAME", 10.0, merchant_name=None)
        assert plaid_sync._transaction_description(txn) == "RAW NAME"


# ---------------------------------------------------------------------------
# sync_item_transactions
# ---------------------------------------------------------------------------

class TestSyncItemTransactions:
    def test_added_transactions_are_stored_with_positive_amount(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        client = MagicMock()
        client.transactions_sync.return_value = fake_sync_response(
            added=[fake_transaction("acct-1", "txn-1", "2026-01-05", "STOP AND SHOP", -42.50)],
        )
        item = {"access_token": "tok", "cursor": None}

        touched = plaid_sync.sync_item_transactions(client, item)

        assert touched == {"acct-1"}
        assert item["cursor"] == "cursor-1"
        store = plaid_sync._load_raw_store("acct-1")
        assert store["txn-1"] == {"date": "2026-01-05", "description": "STOP AND SHOP", "amount": 42.50}

    def test_pending_transactions_are_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        client = MagicMock()
        client.transactions_sync.return_value = fake_sync_response(
            added=[fake_transaction("acct-1", "txn-1", "2026-01-05", "PENDING CHARGE", 10.0, pending=True)],
        )
        plaid_sync.sync_item_transactions(client, {"access_token": "tok", "cursor": None})
        assert plaid_sync._load_raw_store("acct-1") == {}

    def test_removed_transactions_are_deleted_from_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        plaid_sync._save_raw_store("acct-1", {"txn-1": {"date": "2026-01-01", "description": "OLD", "amount": 5.0}})

        client = MagicMock()
        client.transactions_sync.return_value = fake_sync_response(removed=[fake_removed("acct-1", "txn-1")])
        plaid_sync.sync_item_transactions(client, {"access_token": "tok", "cursor": None})

        assert plaid_sync._load_raw_store("acct-1") == {}

    def test_paginates_while_has_more(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        client = MagicMock()
        client.transactions_sync.side_effect = [
            fake_sync_response(
                added=[fake_transaction("acct-1", "txn-1", "2026-01-01", "FIRST PAGE", 1.0)],
                next_cursor="cursor-page-2", has_more=True,
            ),
            fake_sync_response(
                added=[fake_transaction("acct-1", "txn-2", "2026-01-02", "SECOND PAGE", 2.0)],
                next_cursor="cursor-final", has_more=False,
            ),
        ]
        item = {"access_token": "tok", "cursor": None}
        plaid_sync.sync_item_transactions(client, item)

        assert item["cursor"] == "cursor-final"
        store = plaid_sync._load_raw_store("acct-1")
        assert set(store.keys()) == {"txn-1", "txn-2"}


# ---------------------------------------------------------------------------
# write_categorized_csv
# ---------------------------------------------------------------------------

class TestWriteCategorizedCsv:
    def test_writes_categorized_csv_with_year_month(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        plaid_sync._save_raw_store("acct-1", {
            "txn-1": {"date": "2026-02-10", "description": "SHELL OIL", "amount": 40.0},
            "txn-2": {"date": "2026-01-05", "description": "STOP AND SHOP", "amount": 80.0},
        })

        def fake_categorize_with_prompt(model, prompt, transactions, transaction_ids=None):
            return [
                {"raw_transaction": str(t), "description": t[1], "date": t[0], "amount": t[2], "category": "TEST"}
                for t in transactions
            ]

        monkeypatch.setattr(categorize, "categorize_with_prompt", fake_categorize_with_prompt)

        count = plaid_sync.write_categorized_csv(MagicMock(), "acct-1", "Charles Schwab")
        assert count == 2

        df = pd.read_csv(tmp_path / "acct-1_categorized.csv")
        assert list(df["year_month"]) == ["2026-01", "2026-02"]  # sorted by date ascending
        assert set(df["category"]) == {"TEST"}
        assert list(df["transaction_id"]) == ["txn-2", "txn-1"]  # aligned with sorted-by-date order

    def test_always_uses_generic_prompt(self, tmp_path, monkeypatch):
        # Per-institution prompt tuning (bank-specific few-shot hints) was
        # replaced by the generic categorize_prompt plus
        # utils.load_local_category_hints() — every institution shares one
        # prompt now, regardless of the institution_name argument.
        monkeypatch.setattr(plaid_sync, "PLAID_FOLDER", str(tmp_path))
        plaid_sync._save_raw_store("acct-1", {
            "txn-1": {"date": "2026-01-05", "description": "GUSTO", "amount": 100.0},
        })

        seen_prompts = []

        def fake_categorize_with_prompt(model, prompt, transactions, transaction_ids=None):
            seen_prompts.append(prompt)
            return [{"description": t[1], "date": t[0], "amount": t[2], "category": "WAGES"} for t in transactions]

        monkeypatch.setattr(categorize, "categorize_with_prompt", fake_categorize_with_prompt)

        plaid_sync.write_categorized_csv(MagicMock(), "acct-1", "Charles Schwab")
        assert seen_prompts == [categorize.categorize_prompt]


# ---------------------------------------------------------------------------
# sync_all_items — freshness throttling (last_synced_at vs max_age)
# ---------------------------------------------------------------------------

def _item(name, last_synced_at=None):
    return {
        "item_id": name, "access_token": "tok", "institution_name": name,
        "accounts": [], "cursor": None, "last_synced_at": last_synced_at,
    }


class TestSyncAllItemsFreshness:
    def test_no_items_returns_early_without_building_client(self):
        with patch("plaid_sync.load_items", return_value={}), \
             patch("plaid_sync.get_plaid_client") as mock_client:
            plaid_sync.sync_all_items(MagicMock())
            assert not mock_client.called

    def test_fresh_item_is_skipped(self):
        fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        items = {"a": _item("Fresh Bank", last_synced_at=fresh)}
        with patch("plaid_sync.load_items", return_value=items), \
             patch("plaid_sync.save_items"), \
             patch("plaid_sync.get_plaid_client") as mock_client, \
             patch("plaid_sync.sync_item_transactions") as mock_sync_item, \
             patch("plaid_sync.write_categorized_csv", return_value=0):
            plaid_sync.sync_all_items(MagicMock(), max_age=timedelta(hours=24))
            assert not mock_client.called
            assert not mock_sync_item.called

    def test_stale_item_is_synced(self):
        stale = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        items = {"a": _item("Stale Bank", last_synced_at=stale)}
        with patch("plaid_sync.load_items", return_value=items), \
             patch("plaid_sync.save_items"), \
             patch("plaid_sync.get_plaid_client", return_value=MagicMock()) as mock_client, \
             patch("plaid_sync.sync_item_transactions", return_value=set()) as mock_sync_item, \
             patch("plaid_sync.write_categorized_csv", return_value=0):
            plaid_sync.sync_all_items(MagicMock(), max_age=timedelta(hours=24))
            assert mock_client.called
            assert mock_sync_item.called
            assert items["a"]["last_synced_at"] is not None

    def test_never_synced_item_is_synced(self):
        items = {"a": _item("Never Bank", last_synced_at=None)}
        with patch("plaid_sync.load_items", return_value=items), \
             patch("plaid_sync.save_items"), \
             patch("plaid_sync.get_plaid_client", return_value=MagicMock()), \
             patch("plaid_sync.sync_item_transactions", return_value=set()) as mock_sync_item, \
             patch("plaid_sync.write_categorized_csv", return_value=0):
            plaid_sync.sync_all_items(MagicMock(), max_age=timedelta(hours=24))
            assert mock_sync_item.called

    def test_client_built_once_for_multiple_stale_items(self):
        stale = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        items = {"a": _item("Bank A", last_synced_at=stale), "b": _item("Bank B", last_synced_at=stale)}
        with patch("plaid_sync.load_items", return_value=items), \
             patch("plaid_sync.save_items"), \
             patch("plaid_sync.get_plaid_client", return_value=MagicMock()) as mock_client, \
             patch("plaid_sync.sync_item_transactions", return_value=set()), \
             patch("plaid_sync.write_categorized_csv", return_value=0):
            plaid_sync.sync_all_items(MagicMock(), max_age=timedelta(hours=24))
            assert mock_client.call_count == 1

    def test_max_age_zero_forces_sync_even_if_recent(self):
        just_synced = datetime.now(timezone.utc).isoformat()
        items = {"a": _item("Recent Bank", last_synced_at=just_synced)}
        with patch("plaid_sync.load_items", return_value=items), \
             patch("plaid_sync.save_items"), \
             patch("plaid_sync.get_plaid_client", return_value=MagicMock()), \
             patch("plaid_sync.sync_item_transactions", return_value=set()) as mock_sync_item, \
             patch("plaid_sync.write_categorized_csv", return_value=0):
            plaid_sync.sync_all_items(MagicMock(), max_age=timedelta(0))
            assert mock_sync_item.called
