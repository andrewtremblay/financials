"""
plaid_sync.py — Pull new transactions for every linked Plaid item and
(re)generate categorized CSVs in data/plaid/.

Each item remembers when it was last synced (`last_synced_at`). Items synced
more recently than `max_age` are skipped, so callers (e.g. `main.py --source
plaid`, whose default mode calls this on every run) don't hit the live Plaid
API — and on a Production Plaid account, incur per-item costs — more often
than needed. Pass `max_age=timedelta(0)` to force a fetch regardless of
freshness (this is what running `uv run plaid_sync.py` directly does).

Usage:
    uv run plaid_sync.py [--max-age-hours N]
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from plaid.model.transactions_sync_request import TransactionsSyncRequest

import categorize
from plaid_client import get_plaid_client, load_items, save_items
from utils import export_to_csv

load_dotenv()

PLAID_FOLDER = "data/plaid"
DEFAULT_MAX_AGE = timedelta(days=1)


def _raw_store_path(account_id: str) -> Path:
    return Path(PLAID_FOLDER) / f"{account_id}.json"


def _load_raw_store(account_id: str) -> dict:
    path = _raw_store_path(account_id)
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _save_raw_store(account_id: str, store: dict) -> None:
    os.makedirs(PLAID_FOLDER, exist_ok=True)
    with open(_raw_store_path(account_id), "w") as f:
        json.dump(store, f, indent=2)


def _transaction_description(txn) -> str:
    return txn.merchant_name or txn.name


def sync_item_transactions(client, item: dict) -> set[str]:
    """
    Pull all new/modified/removed transactions for one item via /transactions/sync
    and merge them into each linked account's raw store on disk.
    Updates item['cursor'] in place. Returns the set of touched account_ids.
    """
    stores: dict[str, dict] = {}
    cursor = item.get("cursor")
    has_more = True

    while has_more:
        # cursor must be omitted (not None) on the very first sync for a new item
        kwargs = {"cursor": cursor} if cursor else {}
        request = TransactionsSyncRequest(access_token=item["access_token"], **kwargs)
        response = client.transactions_sync(request)

        for txn in list(response.added) + list(response.modified):
            if txn.pending:
                continue
            store = stores.setdefault(txn.account_id, _load_raw_store(txn.account_id))
            store[txn.transaction_id] = {
                "date": str(txn.date),
                "description": _transaction_description(txn),
                "amount": abs(txn.amount),
            }

        for removed in response.removed:
            store = stores.setdefault(removed.account_id, _load_raw_store(removed.account_id))
            store.pop(removed.transaction_id, None)

        cursor = response.next_cursor
        has_more = response.has_more

    item["cursor"] = cursor
    for account_id, store in stores.items():
        _save_raw_store(account_id, store)
    return set(stores.keys())


def write_categorized_csv(model, account_id: str, institution_name: str) -> int:
    """
    Rebuild data/plaid/<account_id>_categorized.csv from the account's raw
    transaction store. institution_name is currently unused for prompt
    routing — per-institution prompt tuning (bank-specific few-shot hints)
    was replaced by the generic categorize_prompt plus
    utils.load_local_category_hints() (a gitignored local file), so every
    institution shares one prompt now; kept as a parameter since callers
    already have it on hand and a future per-institution need may return.
    Returns the number of transactions written.
    """
    store = _load_raw_store(account_id)
    sorted_items = sorted(store.items(), key=lambda kv: kv[1]["date"])
    transaction_ids = [transaction_id for transaction_id, _ in sorted_items]
    transactions = [
        [txn["date"], txn["description"], txn["amount"]]
        for _, txn in sorted_items
    ]
    categorized_data = categorize.categorize_with_prompt(model, categorize.categorize_prompt, transactions, transaction_ids)
    for record, transaction_id in zip(categorized_data, transaction_ids):
        record["transaction_id"] = transaction_id
        record["year_month"] = record["date"][:7]  # ISO date -> YYYY-MM

    output_csv = os.path.join(PLAID_FOLDER, f"{account_id}_categorized.csv")
    export_to_csv(categorized_data, output_csv)
    return len(categorized_data)


def sync_all_items(model, max_age: timedelta = DEFAULT_MAX_AGE) -> None:
    items = load_items()

    if not items:
        print("No linked Plaid items found. Run `uv run plaid_link.py` first.")
        return

    now = datetime.now(timezone.utc)
    client = None  # lazily built — no need for credentials if every item is still fresh

    for item in items.values():
        last_synced_at = item.get("last_synced_at")
        age = now - datetime.fromisoformat(last_synced_at) if last_synced_at else None
        touched_accounts: set[str] = set()

        if age is not None and age < max_age:
            print(f"{item['institution_name']}: synced {age.total_seconds() / 3600:.1f}h ago, skipping (< {max_age}).")
        else:
            if client is None:
                client = get_plaid_client()
            print(f"Syncing {item['institution_name']}...")
            touched_accounts = sync_item_transactions(client, item)
            item["last_synced_at"] = now.isoformat()

        # Even if nothing new came in this sync (or it was skipped), keep every
        # linked account's CSV up to date (covers accounts with no new activity).
        all_account_ids = {a["account_id"] for a in item["accounts"]} | touched_accounts
        for account_id in all_account_ids:
            count = write_categorized_csv(model, account_id, item["institution_name"])
            account_name = next(
                (a["name"] for a in item["accounts"] if a["account_id"] == account_id),
                account_id,
            )
            print(f"  {account_name}: {count} transactions")

    save_items(items)
    print("\nDone.")


if __name__ == "__main__":
    import argparse

    from analyze_pdf import resolve_model  # lazy: avoids pulling in the LLM stack for importers that don't need it

    parser = argparse.ArgumentParser(description="Pull new transactions from all linked Plaid accounts.")
    parser.add_argument(
        "--max-age-hours", type=float, default=0.0,
        help="Skip items synced within this many hours (default: 0 — always sync, since this is an explicit manual run)",
    )
    args = parser.parse_args()

    sync_all_items(resolve_model(), max_age=timedelta(hours=args.max_age_hours))
