"""
Tests for memo.py's chain-signature-based memoization.

Run with: uv run pytest test_memo.py -v
"""
import sys
from types import SimpleNamespace

import pytest

# Other test files replace `memo` in sys.modules with a MagicMock (a defensive
# precaution copied across test files, since memo.py's real module-level code
# reads the on-disk cache file at import time). sys.modules is process-global,
# so when the whole suite runs together that mock can leak into this file —
# force a real import here since this file tests memo.py's actual logic.
sys.modules.pop("memo", None)

import memo  # noqa: E402
from memo import _chain_signature  # noqa: E402


class FakeChatOpenAI:
    def __init__(self, model_name):
        self.model_name = model_name


class FakeOllama:
    def __init__(self, model):
        self.model = model


def fake_chain(template, model):
    return SimpleNamespace(first=SimpleNamespace(template=template), middle=[model], last=SimpleNamespace())


# ---------------------------------------------------------------------------
# _chain_signature
# ---------------------------------------------------------------------------

class TestChainSignature:
    def test_stable_across_equivalent_separately_built_chains(self):
        # Regression test: str(chain) embeds unstable object reprs (e.g. ChatOpenAI's
        # internal http client memory addresses), which used to make this differ on
        # every process run even for identical prompt+model config.
        chain1 = fake_chain("categorize {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        chain2 = fake_chain("categorize {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        assert _chain_signature(chain1) == _chain_signature(chain2)

    def test_differs_for_different_prompt_template(self):
        chain1 = fake_chain("prompt A {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        chain2 = fake_chain("prompt B {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        assert _chain_signature(chain1) != _chain_signature(chain2)

    def test_differs_for_different_model_name(self):
        chain1 = fake_chain("prompt {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        chain2 = fake_chain("prompt {transaction}", FakeChatOpenAI("gpt-4o"))
        assert _chain_signature(chain1) != _chain_signature(chain2)

    def test_differs_for_different_model_class(self):
        chain1 = fake_chain("prompt {transaction}", FakeChatOpenAI("same-name"))
        chain2 = fake_chain("prompt {transaction}", FakeOllama("same-name"))
        assert _chain_signature(chain1) != _chain_signature(chain2)

    def test_falls_back_to_model_attribute(self):
        # OllamaLLM/ChatAnthropic expose `.model` instead of `.model_name`
        chain = fake_chain("prompt {transaction}", FakeOllama("gemma2:27b"))
        assert "gemma2:27b" in _chain_signature(chain)


# ---------------------------------------------------------------------------
# memoize_description_to_file
# ---------------------------------------------------------------------------

class TestMemoizeDescriptionToFile:
    def test_cache_hit_skips_function_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memo, "memoized_description_data", {})
        monkeypatch.setattr(memo, "MEMO_DESCRIPTIONS_FILE", tmp_path / "cache.json")

        calls = []

        @memo.memoize_description_to_file
        def fake_invoke(chain, description):
            calls.append(description)
            return "RESULT"

        chain = fake_chain("prompt {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        assert fake_invoke(chain, "Coffee Shop") == "RESULT"
        assert fake_invoke(chain, "Coffee Shop") == "RESULT"
        assert calls == ["Coffee Shop"]  # second call was cached, function not re-invoked

    def test_different_prompts_do_not_shadow_each_other(self, tmp_path, monkeypatch):
        # Regression test for the bug where the plain description-only cache key
        # let whichever prompt ran first shadow every other prompt's result for
        # the same description (e.g. a Schwab-specific prompt correctly returning
        # WAGES getting hidden behind a generic prompt's earlier "INPUT NEEDED").
        monkeypatch.setattr(memo, "memoized_description_data", {})
        monkeypatch.setattr(memo, "MEMO_DESCRIPTIONS_FILE", tmp_path / "cache.json")

        results = {"schwab {transaction}": "WAGES", "generic {transaction}": "INPUT NEEDED"}

        @memo.memoize_description_to_file
        def fake_invoke(chain, description):
            return results[chain.first.template]

        chain_schwab = fake_chain("schwab {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        chain_generic = fake_chain("generic {transaction}", FakeChatOpenAI("gpt-4o-mini"))

        assert fake_invoke(chain_schwab, "ASF PAYROLL") == "WAGES"
        assert fake_invoke(chain_generic, "ASF PAYROLL") == "INPUT NEEDED"
        # Calling schwab again for the same description must still return WAGES,
        # not get shadowed by generic's later write.
        assert fake_invoke(chain_schwab, "ASF PAYROLL") == "WAGES"

    def test_cache_persists_across_separately_constructed_equivalent_chains(self, tmp_path, monkeypatch):
        # Regression test: simulates two separate accounts/processes each building
        # their own (but logically equivalent) chain instance for the same prompt.
        monkeypatch.setattr(memo, "memoized_description_data", {})
        monkeypatch.setattr(memo, "MEMO_DESCRIPTIONS_FILE", tmp_path / "cache.json")

        calls = []

        @memo.memoize_description_to_file
        def fake_invoke(chain, description):
            calls.append(description)
            return "CACHED"

        chain1 = fake_chain("prompt {transaction}", FakeChatOpenAI("gpt-4o-mini"))
        chain2 = fake_chain("prompt {transaction}", FakeChatOpenAI("gpt-4o-mini"))  # separate object, same config
        fake_invoke(chain1, "Same Description")
        fake_invoke(chain2, "Same Description")
        assert calls == ["Same Description"]
