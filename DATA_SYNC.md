# Data Sync — Plaid → Google Sheet

How Plaid transaction data flows into the household budget Google Sheet
([spreadsheet](https://docs.google.com/spreadsheets/d/1oCSgGmsuizUfhpp-74RJrDP3OBlmkPWY682CloOf42E)),
and how to fix it when a transaction lands in the wrong place.

## Pipeline overview

```
Plaid (linked accounts)
  → plaid_sync.py            pulls transactions, categorizes via categorize.py,
                              writes data/plaid/<account_id>_categorized.csv
  → sheets_sync.py            aggregates categorized CSVs per month, maps
                              categories to sheet line items via
                              sheet_category_map.py, writes one tab per month
```

`plaid_sync.py` runs daily on a local schedule (below). `sheets_sync.py` is
run manually — it's a separate step so a bad categorization can be caught
and fixed in `categorize.py`/`sheet_category_map.py` before it's written to
the sheet, rather than auto-publishing every day.

## Daily Plaid fetch (local launchd job)

A macOS LaunchAgent runs `uv run plaid_sync.py` every morning to keep
`data/plaid/*_categorized.csv` current:

- **Plist:** `~/Library/LaunchAgents/com.andrewtremblay.financials.plaidsync.plist`
- **Schedule:** daily at 7:00 AM (only fires if the Mac is on and awake)
- **Logs:** `~/Library/Logs/financials-plaid-sync.log`
- **Scope:** fetch + categorize only — does **not** touch the Google Sheet

Useful commands:

```bash
# check status / last run
launchctl print gui/$(id -u)/com.andrewtremblay.financials.plaidsync

# run it immediately, outside the schedule
launchctl kickstart gui/$(id -u)/com.andrewtremblay.financials.plaidsync

# change the time: edit the plist's Hour/Minute, then reload
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.andrewtremblay.financials.plaidsync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.andrewtremblay.financials.plaidsync.plist

# disable entirely
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.andrewtremblay.financials.plaidsync.plist
```

This is a **local** job — it only exists on this Mac and only runs while
it's on. It was deliberately not set up as a cloud-scheduled routine because
`plaid_sync.py` needs `plaid_items.json` (live Plaid access tokens) and the
OpenAI key, both local secrets that are gitignored and not in the repo a
cloud sandbox would check out.

## Categorization (`categorize.py`)

Transactions are categorized by an LLM (Ollama `gemma2:27b` if running
locally, else OpenAI `gpt-4o-mini` — see `resolve_model()` in
`analyze_pdf.py`), but `classify_boilerplate()` intercepts known
description/amount patterns first and skips the LLM call entirely. This
covers two kinds of cases:

1. **Structural boilerplate** — "Online Banking transfer to SAV...",
   "Mobile Banking payment to CRD..." — deterministic bank-statement
   language the LLM was inconsistent on (frequently punting to
   `INPUT NEEDED` even at temperature 0).
2. **Specific merchants/deposits the LLM can't know** — e.g. "Clckpay" is
   the 1 Cityview HOA fee, "Deposit Mobile Banking" is Banneker's paycheck,
   "690 Adams St" deposits are credit card payments. These came from
   walking through every `INPUT NEEDED` and miscategorized transaction with
   the account owner directly.

To fix a miscategorized transaction, add a pattern to
`BOILERPLATE_CATEGORY_PATTERNS` in `categorize.py` (most specific patterns
first — order matters, first match wins), then regenerate the CSVs:

```bash
uv run python3 -c "
from analyze_pdf import resolve_model
from plaid_client import load_items
import plaid_sync

model = resolve_model()
items = load_items()
for item in items.values():
    for acct in item['accounts']:
        plaid_sync.write_categorized_csv(model, acct['account_id'], item['institution_name'])
"
```

This is fast and free for any description already in the boilerplate table
or the LLM cache (`memoized_descriptions_to_categories.json`) — only
genuinely new descriptions hit the LLM.

## Category → sheet line item mapping (`sheet_category_map.py`)

`CATEGORY_TO_LINE_ITEM` maps each Plaid category to a `(section, line item)`
on the sheet — e.g. `"GROCERY": ("DAILY LIVING", "Groceries")`. For
hierarchical categories like `"FOOD RESTAURANTS"` or `"FOOD GROCERIES"`
(space-separated = subcategory, per `CLAUDE.md`), `sheets_sync.py` tries the
full string, then the more specific second word, then the parent first
word — so a merchant tagged `FOOD GROCERIES` resolves to Groceries, not
Dining Out, even though `FOOD` alone is also mapped.

`NEEDS_REVIEW_CATEGORIES` lists categories that are **never** auto-mapped,
because the amount legitimately could belong to more than one line and
guessing would silently misallocate money:

- `INSURANCE` — splits across Home/Auto/Health/Umbrella (the specific
  `INSURANCE_AUTO` carve-out for Plymouth Rock is the one exception that
  *is* mapped, since every occurrence so far has been Auto Insurance)
- `HOUSING`, `CHECK`, `DEPOSIT`, `CREDIT` — mixed/unidentifiable purpose,
  no reliable debit/credit sign from Plaid
- `UTILITIES`/`UTILITY` — handled specially in `aggregate_month` instead:
  National Grid bills electric+gas together, so those are split 50/50
  between the two sheet lines; other utility vendors fall back to
  Home > Other
- `INPUT NEEDED` — never resolved by categorization

Anything in `NEEDS_REVIEW_CATEGORIES`, or any category with no mapping at
all, is totaled and printed by `sheets_sync.py` per month instead of being
written to a cell — check that output after every sync.

### Special per-cell rules in `sheets_sync.py`

A few line items have no reliable Plaid signal at all and are excluded from
category aggregation entirely:

- **`FIXED_CELLS`** — forced to an exact constant every sync, regardless of
  Plaid data (currently just Apartment Rental Income, C9/D9 = $2,275).
- **`COPY_PROJECTED_CELLS`** — the ACTUAL cell mirrors whatever the
  PROJECTED cell says (read live each sync), for line items funded from
  untracked accounts or untraceable payment methods: Emergency Fund,
  Retirement (IRA/Roth/MTRS), 401k+Match, Home Projects/Apt. Rent (all
  employer withholding/transfers that never touch a linked account), and
  Cleaning Service (paid via Venmo).

There's also a netting rule specific to the Zus paycheck: the biweekly
$250+$250 auto-transfer to brokerage comes out of the paycheck deposit
itself, so it's subtracted from Take Home Salary (Zus) and counted instead
under Managed Brokerages — otherwise it would be double-counted as both
income and savings.

## Running the sheet sync (`sheets_sync.py`)

```bash
uv run sheets_sync.py --dry-run                       # preview, no credentials needed
uv run sheets_sync.py                                  # write April-Jul 2026 (current default)
uv run sheets_sync.py --months 2026-08                 # a specific month
```

Always `--dry-run` first after a categorization change — it prints every
cell that would be written plus the `[NEEDS REVIEW]` summary, with no
Google API calls, so you can sanity-check before touching the sheet.

Each run:
- Creates a new tab (duplicated from `TEMPLATE_TAB`, currently "March 2026")
  if the month doesn't exist yet, or updates the existing tab in place
- Writes aggregated ACTUAL values, zeroing any line item with no Plaid data
  that month (except `FIXED_CELLS`/`COPY_PROJECTED_CELLS`, which are never
  zeroed)
- Replaces each ACTUAL cell's note with a real per-transaction breakdown —
  date, amount, description, and source account (e.g. `BofA card 0081`) —
  or clears the note if the cell has no data this month
- Is safe to re-run any time (idempotent) — useful after any categorization
  fix to re-push corrected numbers into already-created tabs

### Google Sheets credentials

Auth is via a service account: `service_account.json` in the repo root
(gitignored — contains a private key, never commit it). The service
account's email must have **Editor** access on the sheet (Share → paste the
email → Editor). If `sheets_sync.py` fails with `403 PERMISSION_DENIED`,
that's almost always the sheet not actually being shared with that exact
email — double-check it shows up in the sheet's "people with access" list,
not just typed into the share dialog.
