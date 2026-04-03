# Financials

Analyze Bank and Credit Card Statements into CSVs and Flow Diagrams.

## Setup

This software was written with Python 3.11.4. Anything with 3.11 should be fine.

`uv` is recommended for package installation and virtual environments. See <https://github.com/astral-sh/uv>

`uv add -r requirements.txt`

Install `gemma2:27b` with OllamaLLM (Ollama 0.1.26 or later).

## To Run

1. Add your bank statements to the appropriate folder in the `/data` directory.

2. Run your data directory `uv run analyze_pdf.py`

Expected output is will be something you can add to [sankeymatic](https://sankeymatic.com/build/) and render.

Pass `--open` to automatically open the Sankeymatic diagram in your browser after the run:

```bash
uv run main.py --open
```

## Frontend

A Sankeymatic-based visualization is included in `frontend/build/`. To serve it locally:

```bash
uv run serve_frontend.py
```

Opens at <http://localhost:8080>. On startup it also prints an example deep-link URL that pre-loads a sample diagram.

### Deep linking

Sankeymatic supports loading a diagram via the `?i=` query parameter, which holds a [LZ-compressed](https://github.com/pieroxy/lz-string) diagram string. Use `diagram_to_url()` from `serve_frontend.py` to generate one from any Sankeymatic-formatted text:

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

The diagram format is one flow per line: `Source [Amount] Destination`.

## Coming soon

Better run parameters (choose the llm for classification).

Automatically classify which pdf should belong to each data.
