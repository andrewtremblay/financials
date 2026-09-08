"""
Tests for fmt_sankeymatic in utils.py.

Run with: uv run pytest test_fmt_sankeymatic.py -v
"""
import sys
from unittest.mock import MagicMock

# Patch heavy dependencies before importing utils
for mod in [
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.output_parsers",
    "docling",
    "docling.document_converter",
    "memo",
]:
    sys.modules[mod] = MagicMock()

from utils import fmt_sankeymatic  # noqa: E402


def _lines(output: str) -> set[str]:
    """Return non-empty, non-comment lines from fmt_sankeymatic output."""
    return {line.strip() for line in output.splitlines() if line.strip() and not line.strip().startswith("#")}


# ---------------------------------------------------------------------------
# Wages / income
# ---------------------------------------------------------------------------

def test_wages_flow_into_budget():
    """Income total flows from Wages node into Budget."""
    data = {"WAGES": 3000, "FOOD": 1000}
    out = fmt_sankeymatic(data)
    assert "Wages [3000] Budget" in out


def test_wages_renamed_to_zus_wages():
    """WAGES is display-renamed to 'Zus Wages' via capitalization_map. Since its
    rendered name no longer equals the 'Wages' aggregator, it emits a real leaf
    flow into Wages instead of being self-loop-suppressed."""
    data = {"WAGES": 2500, "FOOD": 500}
    out = fmt_sankeymatic(data)
    assert "Wages [2500] Budget" in out
    assert "Zus Wages [2500] Wages" in out


def test_payroll_renamed_to_banneker_wages():
    """PAYROLL is income (in INCOME_CATEGORIES) and display-renamed to
    'Banneker Wages' via capitalization_map."""
    data = {"PAYROLL": 1600, "FOOD": 400}
    out = fmt_sankeymatic(data)
    assert "Banneker Wages [1600] Wages" in out
    assert "Wages [1600] Budget" in out


def test_zus_two_paychecks():
    """ZUS can have two paycheck sub-sources that both flow into the Zus aggregator,
    which then flows into Wages. Neither paycheck bypasses the Zus node."""
    data = {
        "_map": {"ZUS_FIRST": "ZUS", "ZUS_SECOND": "ZUS"},
        "WAGES": 1000,
        "ZUS": 2000,        # = ZUS_FIRST(1200) + ZUS_SECOND(800), from count_categories
        "ZUS_FIRST": 1200,
        "ZUS_SECOND": 800,
        "FOOD": 500,
    }
    out = fmt_sankeymatic(data)

    # Both paycheck sources flow into the Zus aggregator node
    assert "Zus First [1200] Zus" in out
    assert "Zus Second [800] Zus" in out

    # The Zus aggregator (not a self-loop) flows into Wages
    assert "Zus [2000] Wages" in out

    # WAGES self-loop is still suppressed; total income reaches Budget
    assert "Wages [2500] Wages" not in out
    assert "Wages [3000] Budget" in out

    # Paychecks do not leak directly to Wages or Budget
    assert "Zus First [1200] Wages" not in out
    assert "Budget [1200] Zus First" not in out

    # Savings = total wages(1000+2000) - food(500) = 2500
    assert "Budget [2500] Extra Savings" in out


def test_multiple_income_sources_sum_into_budget():
    """Multiple income categories combine; Wages [total] Budget reflects the sum."""
    data = {"WAGES": 2000, "INCOME": 1000, "FOOD": 500}
    out = fmt_sankeymatic(data)
    assert "Wages [3000] Budget" in out


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

def test_expenses_flow_from_budget():
    """Each expense category emits 'Budget [amount] Category'."""
    data = {"WAGES": 5000, "FOOD": 1200, "HOUSING": 2000}
    out = fmt_sankeymatic(data)
    assert "Budget [1200] Food" in out
    assert "Budget [2000] Housing" in out


def test_expense_amounts_are_formatted_as_title_case():
    """Category names are title-cased in output (underscores → spaces).
    ATM_WITHDRAWAL uses a special capitalization_map entry → 'ATM Withdrawal'.
    Generic multi-word categories (e.g. HOME_REPAIR) become 'Home Repair'.
    """
    data = {"WAGES": 3000, "ATM_WITHDRAWAL": 200, "HOME_REPAIR": 150}
    out = fmt_sankeymatic(data)
    assert "Budget [200] ATM Withdrawal" in out
    assert "Budget [150] Home Repair" in out


# ---------------------------------------------------------------------------
# Savings vs. overspending
# ---------------------------------------------------------------------------

def test_savings_when_income_exceeds_expenses():
    """Extra Savings line appears when wages > total expenses."""
    data = {"WAGES": 5000, "FOOD": 1000, "HOUSING": 2000}
    out = fmt_sankeymatic(data)
    assert "Budget [2000] Extra Savings" in out


def test_explicit_savings_category_distinct_from_extra_savings():
    """The explicit SAVINGS category (money deliberately set aside) and the
    auto-computed leftover (Extra Savings) are separate, distinctly labeled
    outflows — one isn't folded into the other."""
    data = {"WAGES": 5000, "SAVINGS": 1000, "FOOD": 2000}
    out = fmt_sankeymatic(data)
    assert "Budget [1000] Savings" in out
    assert "Budget [2000] Extra Savings" in out


def test_no_savings_line_when_overspending():
    """No Savings line when expenses exceed income."""
    data = {"WAGES": 1000, "FOOD": 1500}
    out = fmt_sankeymatic(data)
    assert "Savings" not in out


def test_overspending_when_expenses_exceed_income():
    """Overspending line appears when total expenses > wages."""
    data = {"WAGES": 1000, "FOOD": 600, "HOUSING": 800}
    out = fmt_sankeymatic(data)
    assert "Overspending [400] Budget" in out


def test_no_overspending_line_when_saving():
    """No Overspending line when income exceeds expenses."""
    data = {"WAGES": 5000, "FOOD": 1000}
    out = fmt_sankeymatic(data)
    assert "Overspending" not in out


# ---------------------------------------------------------------------------
# Needs / Wants subcategories
# ---------------------------------------------------------------------------

def test_subcategory_flows_from_parent_expense():
    """Subcategories flow out of their parent node, not directly from Budget."""
    data = {
        "_map": {"HOUSING": "NEEDS", "FOOD": "NEEDS"},
        "WAGES": 4000,
        "NEEDS": 2500,
        "HOUSING": 1500,
        "FOOD": 1000,
    }
    out = fmt_sankeymatic(data)
    assert "Needs [1500] Housing" in out
    assert "Needs [1000] Food" in out


def test_parent_expense_node_flows_from_budget():
    """The parent expense node (e.g., Needs) appears as a Budget outflow."""
    data = {
        "_map": {"HOUSING": "NEEDS"},
        "WAGES": 4000,
        "NEEDS": 1500,
        "HOUSING": 1500,
    }
    out = fmt_sankeymatic(data)
    assert "Budget [1500] Needs" in out


def test_subcategory_not_emitted_as_direct_budget_outflow():
    """Subcategories are NOT emitted as 'Budget [x] Sub' — only the parent is."""
    # FOOD=1000 mirrors what count_categories produces: all FOOD transactions
    # (800 dining + 200 groceries) accumulate on the parent as well as the sub.
    data = {
        "_map": {"DINING": "FOOD", "GROCERIES": "FOOD"},
        "WAGES": 3000,
        "FOOD": 1000,   # = DINING(800) + GROCERIES(200), from count_categories
        "DINING": 800,
        "GROCERIES": 200,
    }
    out = fmt_sankeymatic(data)
    assert "Budget [1000] Food" in out
    assert "Food [800] Dining" in out
    assert "Food [200] Groceries" in out
    assert "Dining [800] Food" not in out


def test_transportation_counted_under_needs():
    """TRANSPORTATION must flow through Needs, not directly from Budget.
    When it bypasses Needs, savings/overspending are miscalculated."""
    data = {
        "_map": {"HOUSING": "NEEDS", "TRANSPORTATION": "NEEDS"},
        "WAGES": 4000,
        "NEEDS": 2500,       # = HOUSING(1500) + TRANSPORTATION(1000)
        "HOUSING": 1500,
        "TRANSPORTATION": 1000,
    }
    out = fmt_sankeymatic(data)

    # Transportation flows through Needs, not directly from Budget
    assert "Needs [1000] Transportation" in out
    assert "Needs [1500] Housing" in out
    assert "Budget [2500] Needs" in out
    assert "Budget [1000] Transportation" not in out

    # Savings correctly reflects wages minus total Needs (not wages minus Needs+Transportation)
    assert "Budget [1500] Extra Savings" in out


def test_nested_transportation_counted_under_needs():
    """Transportation subcategories (Lyft, Uber, Fuel) all flow through the
    Transportation→Needs→Budget hierarchy.  An uncategorized OTHER expense
    flows directly from Budget as an edge case."""
    data = {
        # UBER and FUEL are known subs of TRANSPORTATION; OTHER is intentionally unmapped
        "_map": {
            "HOUSING": "NEEDS",
            "TRANSPORTATION": "NEEDS",
            "LYFT": "TRANSPORTATION",
            "UBER": "TRANSPORTATION",
            "FUEL": "TRANSPORTATION",
        },
        "WAGES": 4000,
        "NEEDS": 2500,          # = HOUSING(1500) + TRANSPORTATION(1000)
        "HOUSING": 1500,
        "TRANSPORTATION": 1000, # = LYFT(600) + UBER(300) + FUEL(50) + direct(50)
        "LYFT": 600,
        "UBER": 300,
        "FUEL": 50,
        "OTHER": 400,           # edge case: no _map entry → flows straight from Budget
    }
    out = fmt_sankeymatic(data)

    # All transportation subs flow through the hierarchy, not from Budget
    assert "Budget [2500] Needs" in out
    assert "Budget [950] Transportation" not in out  # Transportation doesn't bypass Needs
    assert "Needs [1000] Transportation" in out
    assert "Needs [1500] Housing" in out
    assert "Transportation [600] Lyft" in out
    assert "Transportation [300] Uber" in out
    assert "Transportation [50] Fuel" in out

    # The $50 gap inside Transportation appears as a direct sub-flow, not as Budget→Other
    assert "Transportation [50] Transportation Direct" in out
    assert "Budget [50] Other" not in out

    # OTHER is the edge case: unmapped, so it IS a direct Budget outflow
    assert "Budget [400] Other" in out

    # Savings = wages(4000) - needs(2500) - other(400) = 1100
    assert "Budget [1100] Extra Savings" in out


def test_needs_wants_savings_structure():
    """Full needs/wants/savings flow: income → Wages → Budget → Needs/Wants, remainder → Savings."""
    data = {
        "_map": {"HOUSING": "NEEDS", "FOOD": "NEEDS", "ENTERTAINMENT": "WANTS"},
        "WAGES": 4000,
        "NEEDS": 2000,
        "HOUSING": 1200,
        "FOOD": 800,
        "WANTS": 600,
        "ENTERTAINMENT": 600,
    }
    out = fmt_sankeymatic(data)
    lines = _lines(out)

    assert "Wages [4000] Budget" in lines
    assert "Budget [2000] Needs" in lines
    assert "Budget [600] Wants" in lines
    assert "Needs [1200] Housing" in lines
    assert "Needs [800] Food" in lines
    assert "Wants [600] Entertainment" in lines
    assert "Budget [1400] Extra Savings" in lines


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_break_even_no_savings_no_overspending():
    """When income exactly equals expenses, neither Savings nor Overspending appears."""
    data = {"WAGES": 1000, "FOOD": 1000}
    out = fmt_sankeymatic(data)
    assert "Savings" not in out
    assert "Overspending" not in out


def test_negative_expense_skipped():
    """A net-negative category (refund exceeds purchases) is silently dropped."""
    data = {"WAGES": 3000, "FOOD": -100, "GAS": 500}
    out = fmt_sankeymatic(data)
    assert "Food" not in out
    # Gas still flows normally; savings = 3000 - 500 = 2500
    assert "Budget [500] Gas" in out
    assert "Budget [2500] Extra Savings" in out


def test_zero_amount_expense_not_emitted():
    """A zero-amount category is never emitted as a Budget outflow."""
    data = {"WAGES": 2000, "FOOD": 0, "GAS": 200}
    out = fmt_sankeymatic(data)
    assert "Budget [0] Food" not in out
    assert "Budget [200] Gas" in out


def test_capitalization_map_mbta():
    """MBTA is in the capitalization_map and renders as 'MBTA', not 'Mbta'."""
    data = {"WAGES": 2000, "MBTA": 150}
    out = fmt_sankeymatic(data)
    assert "Budget [150] MBTA" in out


def test_capitalization_map_chatgpt():
    """CHATGPT renders as 'ChatGPT' via the capitalization_map."""
    data = {"WAGES": 2000, "CHATGPT": 20}
    out = fmt_sankeymatic(data)
    assert "Budget [20] ChatGPT" in out


def test_income_category_variant():
    """INCOME (not WAGES) is treated as income and flows into Wages."""
    data = {"INCOME": 1500, "FOOD": 500}
    out = fmt_sankeymatic(data)
    assert "Wages [1500] Budget" in out
    assert "Budget [500] Food" in out
    assert "Budget [1000] Extra Savings" in out


def test_salary_income_category():
    """SALARY is recognized as income."""
    data = {"SALARY": 4000, "HOUSING": 1200}
    out = fmt_sankeymatic(data)
    assert "Wages [4000] Budget" in out


def test_multiple_income_categories_separate_lines():
    """Each non-WAGES income category emits its own → Wages line."""
    data = {"WAGES": 1000, "INCOME": 500, "FOOD": 200}
    out = fmt_sankeymatic(data)
    # INCOME flows into Wages node; WAGES does not self-loop
    assert "Income [500] Wages" in out
    assert "Wages [500] Wages" not in out
    assert "Wages [1500] Budget" in out


def test_caller_dict_not_mutated():
    """fmt_sankeymatic must not modify the caller's data dict."""
    data = {"WAGES": 2000, "FOOD": 500, "_map": {"DINING": "FOOD"}, "DINING": 300}
    original_keys = set(data.keys())
    fmt_sankeymatic(data)
    assert set(data.keys()) == original_keys
    assert "_map" in data  # _map was not popped from original
