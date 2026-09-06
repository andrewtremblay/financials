# Financials

Analyze bank and credit card statements into CSVs and Sankey flow diagrams.

## Setup

Requires Python 3.12. [`uv`](https://github.com/astral-sh/uv) is recommended for package management.

```bash
uv add -r requirements.txt
```

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`. Install them with:

`uv sync`

Install `gemma2:27b` via [Ollama](https://ollama.com) (0.1.26 or later). Alternatively, set `OPENAI_API_KEY` in `.env` to use `gpt-4` or `gpt-4o-mini`.

## To Run

By default, `uv run main.py` only uses **Plaid** — see [Connecting accounts via Plaid](#connecting-accounts-via-plaid-optional) to link accounts first. To use PDF statements instead (or in addition), pass `--source pdf` or `--source all`.

```bash
uv run main.py
```

This default (`--source plaid`) syncs every linked Plaid item (skipping any synced within the last 24h — see `--plaid-max-age-hours`) and prints Sankeymatic-formatted output broken down by month plus a total.

### PDF statements (`--source pdf` or `--source all`)

1. Drop any bank statement PDFs into `data/inbox/`.
2. Run:

```bash
uv run main.py --source pdf
```

The tool automatically identifies each PDF's bank by scanning its content, routes it to the correct subfolder (`data/boa_cc/`, `data/schwab/`, etc.), categorizes every transaction via LLM, and prints Sankeymatic-formatted output broken down by month plus a total.

#### Supported banks

| Bank | Destination folder |
|------|--------------------|
| Bank of America (credit card) | `data/boa_cc/` |
| Schwab (checking) | `data/schwab/` |
| Barclays (credit card) | `data/barclays/` |
| PayPal | `data/paypal/` |

### CLI options

```bash
uv run main.py --open                       # open the total diagram in your browser
uv run main.py --month feb                  # filter browser view to February (any year)
uv run main.py --source pdf                 # PDF statements only, no Plaid
uv run main.py --source all                 # both Plaid and PDF (not deduplicated yet)
uv run main.py --plaid-max-age-hours 0      # force a fresh Plaid sync regardless of last sync time
uv run main.py --inbox-only                 # (--source pdf/all) only data/inbox/, skip bank-specific subfolders
```

### Output

For each detected calendar month the tool prints a Sankeymatic block you can paste into [sankeymatic.com](https://sankeymatic.com/build/), followed by a combined total across all months:

```
====================================================
  January 2026
====================================================
Wages [5431] Budget
...

====================================================
  TOTAL  (2025-12, 2026-01, 2026-02)
====================================================
Wages [16295] Budget
...
```

All transactions are also written to `rollup.csv` with a `year_month` column (`YYYY-MM`) so you can slice and filter the raw data yourself.

## Connecting accounts via Plaid (optional)

Instead of (or alongside) dropping PDF statements in `data/inbox/`, you can link accounts directly via [Plaid](https://plaid.com) and pull transactions from its API.

1. Get API keys from the [Plaid dashboard](https://dashboard.plaid.com/team/keys) and add them to `.env`:

   ```
   PLAID_CLIENT_ID=...
   PLAID_SECRET=...
   PLAID_ENV=sandbox        # or "production"
   ```

2. Link an account (run once per account — Schwab, BoA, Barclays, PayPal, or any other institution Plaid supports):

   ```bash
   uv run plaid_link.py
   ```

   This opens a local page in your browser hosting Plaid's Link UI. Pick your institution, log in, and the linked item (access token + accounts) is saved to `plaid_items.json` (gitignored — it holds live access tokens, treat it like a secret).

   Some larger banks require OAuth. If Link tells you to register a redirect URI, add one in the Plaid dashboard (e.g. `http://localhost:8090/oauth`) and set `PLAID_REDIRECT_URI` in `.env` to match.

3. Run `uv run main.py` (its default `--source plaid` mode). It syncs every linked item via `/transactions/sync`, categorizes new transactions via the same LLM pipeline, and writes `data/plaid/<account_id>_categorized.csv` before building the report.

   Items synced within the last 24h are skipped (no API call) to avoid hitting rate limits or, on a Production Plaid account, per-item costs on every run. Tune this with `--plaid-max-age-hours` (`0` forces a fresh sync every time). To sync without generating a report, you can also run `uv run plaid_sync.py` directly (defaults to always syncing, since running it manually implies you want fresh data now — override with `--max-age-hours`).

If you want PDF statements instead of or alongside Plaid, pass `--source pdf` or `--source all` (see [To Run](#to-run)). Plaid-derived and PDF-derived transactions for the same account are **not** deduplicated yet — if you link an account via Plaid, stop feeding its PDFs into `data/inbox/` to avoid double-counting when using `--source all`.

## Frontend

A local Sankeymatic visualization is included. Serve it with:

```bash
uv run serve_frontend.py
```

Opens at <http://localhost:8080>. `--open` in `main.py` launches this automatically after a run.

### Deep linking

Use `diagram_to_url()` to generate a pre-loaded browser URL from any Sankeymatic string:

```python
from serve_frontend import diagram_to_url

diagram = """\
Wages [3000] Budget
Budget [1200] Housing
Budget [600] Food
Budget [200] Savings
"""

print(diagram_to_url(diagram))
# → http://localhost:8080/?i=<compressed>
```

Flow format: `Source [Amount] Destination` — one per line.

## Testing

Unit tests cover the pure logic — transaction/money/date parsing, category
counting, Sankeymatic formatting, and diagram sizing. They mock the heavy ML
dependencies (LangChain, Docling), so the suite runs in seconds with only
`pandas` installed:

```bash
uv run --with pandas pytest
```

These same tests run automatically in CI on every pull request and on pushes to
`main` (see `.github/workflows/unit-tests.yml`).

### Coverage

Add `--cov` to measure code coverage of the application modules:

```bash
uv run --with pandas pytest --cov --cov-report=term-missing
```

The measured modules are configured under `[tool.coverage.run]` in
`pyproject.toml`. CI also publishes a coverage table to each run's job summary.

## Architecture

| File | Role |
|------|------|
| `analyze_pdf.py` | Main pipeline: PDF → CSV, rollup, monthly Sankey output |
| `main.py` | CLI wrapper (argparse, browser launch) |
| `classify_pdf.py` | Content-based PDF → bank routing (inbox classifier) |
| `categorize.py` | LangChain prompt + LLM categorization |
| `utils.py` | PDF loading, CSV I/O, category counting, Sankeymatic formatting |
| `memo.py` | File-backed memoization for LLM calls and Docling parses |
| `serve_frontend.py` | Local HTTP server + deep-link URL generation |
| `plaid_client.py` | Shared Plaid API client + local item (access token) storage |
| `plaid_link.py` | One-time-per-account browser flow to link a bank/credit card via Plaid |
| `plaid_sync.py` | Explicit `/transactions/sync` pull → categorized CSVs in `data/plaid/` |

## Data flow

```
data/inbox/*.pdf
  → classify_inbox()        content-score each PDF → copy to bank subfolder
  → load_pdf_as_dataframes()  Docling table extraction (memoized)
  → extract_dataframes()    detect date/description/amount columns
  → categorize()            LLM via LangChain (memoized per description)
  → *_categorized.csv       one file per PDF
  → rollup.csv              all sources + year_month column
  → monthly Sankey strings  grouped by inferred calendar month/year
```

Year is inferred from year-bearing dates embedded in the PDF itself (`MM/DD/YYYY` and `Month D, YYYY` patterns). The latest such date found (typically the closing or due date) anchors the statement. Transactions whose month exceeds the anchor month are attributed to the prior year (standard billing-cycle logic).

## Memoization

Two JSON caches persist across runs (not gitignored — handle with care):

| File | Contents |
|------|----------|
| `memoized_descriptions_to_categories.json` | LLM results keyed by transaction description |
| `memoized_files_to_dataframes.json` | Docling parse results keyed by PDF path |

Delete either file to force a full re-run.
