# Financials

Analyze Bank and Credit Card Statements into CSVs and Flow Diagrams.

## Setup

This software was written with Python 3.11.4. Anything with 3.11 should be fine.

`pip install -r requirements.txt`

Install `gemma2:27b` with OllamaLLM (Ollama 0.1.26 or later).

## To Run

1. Add your bank statements to the appropriate folder in the `/data` directory.

2. Run your data directory `python analyze_pdf.py`

Expected output is will be something you can add to [sankeymatic](https://sankeymatic.com/build/) and render.

## Coming soon

Better run parameters (choose the llm for classification).

Direct-to-sankeymatic integration.

Automatically classify which pdf should belong to each data.
