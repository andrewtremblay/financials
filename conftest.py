"""Shared pytest setup.

The application modules (``utils``, ``analyze_pdf``, ``categorize`` and the
per-bank extractors) import heavy, slow, network-y libraries at module import
time — LangChain, Docling, an Ollama/OpenAI client, ``python-dotenv``.  None of
that is needed to unit-test the pure helper functions (money/date parsing,
category counting, Sankeymatic formatting, diagram sizing).

To keep the unit suite fast and hermetic we replace those libraries with
``MagicMock`` stand-ins *before* the application modules are imported.  Only
``pandas`` and ``lzstring`` (plus the standard library) are exercised for real,
so the suite runs without installing the full ML dependency tree.
"""

import sys
from unittest.mock import MagicMock

# Modules replaced with mocks. Every submodule that is imported with
# ``from x.y import z`` must be listed explicitly so the import machinery finds
# it in ``sys.modules`` instead of trying to import the real (absent) package.
_MOCKED_MODULES = [
    "langchain",
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.prompts",
    "langchain_core.output_parsers",
    "langchain_openai",
    "langchain_ollama",
    "docling",
    "docling.document_converter",
    "dotenv",
    "memo",
]

for _mod in _MOCKED_MODULES:
    sys.modules.setdefault(_mod, MagicMock())
