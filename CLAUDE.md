# Financials — Claude Code Guide

## Project Overview

AI-assisted financial statement analyzer. Reads bank/credit card PDFs, extracts transactions via [Docling](https://docling-project.github.io/docling/), categorizes them using an LLM, and outputs [Sankeymatic](https://sankeymatic.com/build/)-compatible budget flow data.

## Running

```bash
uv run analyze_pdf.py
# or equivalently:
uv run main.py
```

Requires Ollama running locally with `gemma2:27b` (default model). OpenAI models (`gpt-4`, `gpt-4o-mini`) are available — set `OPENAI_API_KEY` in `.env` to use them.

Default `--source` is `plaid` — `main()` syncs linked Plaid items (throttled by `--plaid-max-age-hours`, default 24h) and reads only `data/plaid/`. Use `--source pdf` for the PDF-only pipeline described below, or `--source all` for both (see [Plaid Integration](#plaid-integration-optional)).

## Architecture

| File | Role |
|------|------|
| [analyze_pdf.py](analyze_pdf.py) | Main entry point + PDF-to-CSV pipeline (v1/v2) |
| [main.py](main.py) | Thin wrapper that calls `analyze_pdf.main()` |
| [categorize.py](categorize.py) | LangChain prompt + categorization logic |
| [utils.py](utils.py) | PDF loading, CSV I/O, category counting, Sankeymatic formatting |
| [memo.py](memo.py) | File-backed memoization for LLM calls and Docling parses |
| [boa.py](boa.py) / [schwab.py](schwab.py) / [barclays.py](barclays.py) / [paypal.py](paypal.py) | Bank-specific v1 extractors and categorizers |
| [plaid_client.py](plaid_client.py) | Shared Plaid API client + local `plaid_items.json` (access tokens) storage |
| [plaid_link.py](plaid_link.py) | Run once per account: local browser flow to link via Plaid |
| [plaid_sync.py](plaid_sync.py) | Run explicitly (not part of `main()`): pulls `/transactions/sync`, writes `data/plaid/*_categorized.csv` |

## Data Flow

```
data/<bank>/*.pdf
  → load_pdf_as_dataframes() (Docling, memoized)
  → extract_dataframes() (find date/desc/amount columns)
  → categorize() (LLM via LangChain, memoized)
  → *_categorized.csv per PDF
  → rollup.csv (all sources combined)
  → Sankeymatic string (stdout)
```

## Data Directories

Place PDFs in the matching subdirectory (all gitignored):
- `data/boa_cc/` — Bank of America credit card
- `data/schwab/` — Schwab checking
- `data/barclays/` — Barclays credit card
- `data/paypal/` — PayPal
- `data/plaid/` — populated by `plaid_sync.py`, not PDFs (raw per-account JSON stores + `*_categorized.csv`)

## Plaid Integration (optional, default source)

Linked accounts (any institution Plaid supports — Schwab, BoA, Barclays, PayPal, etc.) are the default source, an alternative/supplement to PDF statements:
- `uv run plaid_link.py` — one-time-per-account browser flow; saves access tokens to `plaid_items.json` (gitignored, contains live credentials)
- `plaid_sync.sync_all_items(model, max_age)` — pulls via `/transactions/sync`; categorizes via the same `categorize.categorize()` used by the PDF pipeline, writes `data/plaid/<account_id>_categorized.csv` with an exact `year_month` column (from Plaid's ISO dates, no statement-date inference needed). Each item records `last_synced_at`; items synced more recently than `max_age` are skipped (no API call).
- `main(source="plaid")` (the default) calls this on every run, throttled by `--plaid-max-age-hours` (default 24h) — so `uv run main.py` reflects roughly-fresh Plaid data without hitting the API/Production per-item costs on every single invocation. Pass `--plaid-max-age-hours 0` (or run `uv run plaid_sync.py` directly, which defaults to always-sync) to force a fresh pull.
- No dedup between Plaid and PDF sources for the same account when using `--source all` — planned as a future parameter, not yet implemented; the user is responsible for not double-feeding both in the meantime

## Memoization

Two JSON cache files persist across runs (gitignored via `.gitignore` for old names, but the current files are **not** gitignored — be careful):
- `memoized_descriptions_to_categories.json` — LLM category results keyed by transaction description
- `memoized_files_to_dataframes.json` — Docling parse results keyed by PDF path

Delete these files to force a full re-run.

## Categories & Output

- Categories are uppercase strings (e.g. `FOOD`, `GAS`, `SUBSCRIPTION`)
- Space-separated categories encode hierarchy: `FOOD RESTAURANTS` means `RESTAURANTS` is a subcategory of `FOOD`
- `IGNORE_CATEGORY` list in [utils.py:116](utils.py#L116) suppresses double-counting (transfers, payments, etc.)
- `INCOME_CATEGORIES` in [utils.py:176](utils.py#L176) defines what counts as income for the Sankey diagram

## Environment

- Python 3.12 (managed via `uv`)
- `.env` file for `OPENAI_API_KEY` (optional; only needed for OpenAI models)
- Install dependencies: `uv sync` (all dependencies are declared in `pyproject.toml` / `uv.lock`)

## Key Patterns

- **v1 pipeline**: fast regex extraction per bank (brittle, bank-specific parsers)
- **v2 pipeline**: Docling table extraction (slower, more general — currently active in `main()`)
- The active model is hardcoded in [analyze_pdf.py:188](analyze_pdf.py#L188) — change `model = models["gemma2:27b"]` to switch
- Column detection in [analyze_pdf.py:56-110](analyze_pdf.py#L56-L110) uses fuzzy/regex matching to handle PDF-to-table variance across banks
