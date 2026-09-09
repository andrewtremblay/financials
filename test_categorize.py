"""
Tests for categorize.py's classify_boilerplate — deterministic categorization
of known boilerplate bank descriptions, checked before any LLM call.

Run with: uv run pytest test_categorize.py -v
"""
import sys
from unittest.mock import MagicMock

# Patch heavy dependencies before importing categorize, same convention as
# test_utils.py/test_analyze_pdf.py.
for mod in [
    "langchain_openai",
    "langchain_ollama",
    "langchain_anthropic",
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "docling",
    "docling.document_converter",
    "memo",
    "dotenv",
]:
    sys.modules[mod] = MagicMock()

# Some other test modules (e.g. test_analyze_pdf.py, test_plaid_sync.py)
# stub out "categorize" itself with a MagicMock, since they only need it
# importable, not real — sys.modules is process-global, so if one of those
# files was collected first, `import categorize` below would silently
# return their mock instead of this module's actual functions. Swap in a
# fresh real import just long enough to grab what we need, then restore
# whatever was there before — those other files' own module-level mocking
# runs once at collection time and expects sys.modules["categorize"] to
# still be their mock afterward, not permanently replaced by a real module.
_previous_categorize_module = sys.modules.pop("categorize", None)
import categorize as _real_categorize  # noqa: E402
classify_boilerplate = _real_categorize.classify_boilerplate
if _previous_categorize_module is not None:
    sys.modules["categorize"] = _previous_categorize_module
else:
    del sys.modules["categorize"]


class TestInsperiPayroll:
    """"ASF, DBA INSPERI PAYROLL" deposits are Zus's paycheck (twice
    monthly, ~$4880-$4933), except the fixed $250 split routed separately to
    the Emergency Fund. This employer/payroll-processor pair never applies
    to Banneker's paycheck, which always arrives under a completely
    different description (TRINET HR CORPOR PAYROLL, Gusto, ...) — without a
    hardcoded rule the LLM had to guess WAGES vs PAYROLL from the
    description alone and got it wrong almost every time (2026-09-09,
    user-reported: "you put the zus INSPERI PAYROLL in the wrong place" for
    August)."""

    def test_main_paycheck_amount_is_wages(self):
        assert classify_boilerplate("ASF, DBA INSPERI PAYROLL 260812~ Tran: A", 4932.69) == "WAGES"

    def test_varying_paycheck_amounts_are_all_wages(self):
        for amount in (4880.47, 4909.95, 4913.40, 4931.33, 4932.69):
            assert classify_boilerplate("ASF, DBA INSPERI PAYROLL 260113~ Tran: A", amount) == "WAGES"

    def test_exact_250_split_is_emergency_fund_not_wages(self):
        assert classify_boilerplate("ASF, DBA INSPERI PAYROLL 260812~ Tran: A", 250.00) == "EMERGENCY_FUND_ZUS"

    def test_case_insensitive_match(self):
        assert classify_boilerplate("asf, dba insperi payroll 260812~ tran: a", 4932.69) == "WAGES"

    def test_no_amount_still_resolves_to_wages(self):
        # amount can be None (e.g. a caller that doesn't have it handy) --
        # only the exact $250 case needs the amount to disambiguate.
        assert classify_boilerplate("ASF, DBA INSPERI PAYROLL 260812~ Tran: A", None) == "WAGES"


class TestUnrelatedBanneckerPayroll:
    """Banneker's real paycheck descriptions must be unaffected -- they
    never contain "insperi payroll" and should keep falling through to
    whatever already handles them (the LLM, since none of these specific
    strings have their own boilerplate pattern)."""

    def test_trinet_not_matched_by_insperi_rule(self):
        assert classify_boilerplate("TRINET HR CORPOR PAYROLL 250815~ Tran: A", 4900.0) != "WAGES"

    def test_gusto_not_matched_by_insperi_rule(self):
        assert classify_boilerplate("Gusto", 4900.0) != "WAGES"
