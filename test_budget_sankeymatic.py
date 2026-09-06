"""
Tests for budget_sankeymatic.py.

The fixtures here deliberately reproduce the structural traits of a real
month (2026-06) that surfaced two bugs during manual review (2026-07-31):
spending + saving more than was earned that month (income < total outflow),
and multiple expense sections each having their own "Other" catch-all line
item with a nonzero amount. Both are realistic, recurring shapes — not
edge cases — so they're captured here as regression fixtures rather than
relying on live Plaid data (which drifts day to day) to catch a regression.

Run with: uv run pytest test_budget_sankeymatic.py -v
"""
import pytest

import custom_budget_classification
import untracked_income
from budget_sankeymatic import to_sankeymatic


@pytest.fixture(autouse=True)
def isolated_budget_classification_file(tmp_path, monkeypatch):
    """to_sankeymatic(group_by="classification") reads budget_classification.py,
    which consults custom_budget_classification.py's override store — never
    touch the real one."""
    monkeypatch.setattr(custom_budget_classification, "CUSTOM_BUDGET_CLASSIFICATION_FILE", tmp_path / "custom_budget_classification.json")


@pytest.fixture(autouse=True)
def isolated_untracked_income_file(tmp_path, monkeypatch):
    """to_sankeymatic reads untracked_income.py's override store for every
    Savings line item — never touch the real one."""
    monkeypatch.setattr(untracked_income, "UNTRACKED_INCOME_FILE", tmp_path / "untracked_income_overrides.json")


def _line_item(label, row, actual, projected=None):
    return {
        "label": label, "row": row, "projected": projected, "actual": actual,
        "difference": (actual - projected) if projected is not None else None,
        "is_fixed": False, "is_copy_projected": False, "transactions": [],
    }


def _section(key, label, kind, line_items, other_actual=None):
    section = {"key": key, "label": label, "kind": kind, "line_items": line_items}
    if other_actual is not None:
        section["other"] = _line_item("Other", 99, other_actual)
    return section


def make_month_json(sections):
    return {"year_month": "2026-06", "sections": sections, "needs_review": []}


class TestBudgetBalance:
    """Budget's total inflow (income) must balance against total OUTFLOW —
    expenses AND savings both leave Budget. A prior version only compared
    income against expenses, silently ignoring savings as an outflow, which
    left Budget structurally unbalanced (a visible gap between the income
    ribbons and the rest of the block) any month spending+saving exceeded
    income (2026-07-31 regression)."""

    def test_overspending_when_expenses_and_savings_exceed_income(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 8873.32)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 1000.0)]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 8000.0)]),
        ])
        # income 8873.32; outflow = 1000 (savings) + 8000 (expense) = 9000 -> overspending 126.68
        # "Other Savings" (not Emergency Fund/Managed Brokerages/retirement)
        # so it gets no untracked-income offset — genuinely counts as outflow.
        text = to_sankeymatic(month)
        assert "Overspending [126.68] Budget" in text
        assert ":Overspending #ef4444" in text
        assert "Underspending" not in text

    def test_savings_alone_can_trigger_overspending(self):
        """Even with expenses at zero, saving more than you earned that
        month must still be flagged — this is exactly the bug: the old code
        never looked at savings at all when computing the balance."""
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 1000.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 1500.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Overspending [500.00] Budget" in text

    def test_underspending_when_income_exceeds_outflow(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 5000.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 1000.0)]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Underspending" in text
        assert "Budget [2000.00] Underspending" in text
        assert "Overspending" not in text

    def test_exact_balance_emits_neither(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 1000.0)]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 1000.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Overspending" not in text
        assert "Underspending" not in text

    def test_near_exact_balance_within_epsilon_emits_neither(self):
        """A cent of float-summation drift shouldn't render a spurious
        Overspending/Underspending sliver on a month that's really a break
        even (2026-08-01, user-specified: "if it's a perfect break even,
        don't show it")."""
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 1000.005)]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 1000.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Overspending" not in text
        assert "Underspending" not in text

    def test_retirement_contributions_get_a_matching_untracked_income_flow(self):
        """401k/IRA contributions are deducted before the paycheck becomes
        take-home pay — without a matching inflow they'd read as
        overspending even though they're not real overspending
        (2026-07-31, user-specified)."""
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 5000.0)]),
            _section("savings", "Savings", "income_savings", [
                _line_item("Retirement (401k + Match)", 18, 1136.0),
                _line_item("Retirement (MTRS)", 17, 730.0),
            ]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 5000.0)]),
        ])
        text = to_sankeymatic(month)
        # income 5000 + untracked 1136 + 730 = 6866; outflow = 1136+730+5000 = 6866 -> balanced, no false overspending
        assert "Overspending" not in text
        assert "Untracked Income [1136.00] Budget" in text
        assert "Untracked Income [730.00] Budget" in text
        assert "Savings [1136.00] Retirement (401k + Match)" in text
        assert "Savings [730.00] Retirement (MTRS)" in text

    def test_emergency_fund_and_managed_brokerages_get_untracked_income_flow(self):
        """Both are post-tax, but split directly out of the paycheck as a
        separate destination BEFORE the "Take Home Salary" deposit Plaid
        ever sees (Emergency Fund: a distinct $250 payroll deposit;
        Managed Brokerages: explicitly netted out of Take Home Salary (Zus)
        upstream in budget_aggregate.py) — so, like retirement, this money
        was never tracked income and shouldn't read as overspending
        (2026-08-01, user-specified: determined from the actual transaction
        source/category, not assumed)."""
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 300.0)]),
            _section("savings", "Savings", "income_savings", [
                _line_item("Emergency Fund", 16, 500.0),
                _line_item("Managed Brokerages", 19, 200.0),
            ]),
        ])
        text = to_sankeymatic(month)
        assert "Overspending" not in text
        assert "Untracked Income [500.00] Budget" in text
        assert "Untracked Income [200.00] Budget" in text

    def test_other_savings_lines_do_not_get_untracked_income_treatment(self):
        """Home Projects (Apt. Rent) and Other Savings are funded from
        already-tracked income (rental income / a checking-account transfer),
        unlike retirement/Emergency Fund/Managed Brokerages — they should
        still count as real outflow with no offsetting inflow."""
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 300.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 500.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Untracked Income" not in text
        assert "Overspending [200.00] Budget" in text

    def test_custom_rule_turns_on_untracked_income_for_a_normally_tracked_label(self):
        """Confirms to_sankeymatic actually consults untracked_income.py's
        override store (not just the hardcoded default set) — user-added a
        rule marking "Other Savings" as untracked for this month."""
        untracked_income.add_rule("Other Savings", True, "current", "2026-06")
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 300.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 500.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Untracked Income [500.00] Budget" in text
        assert "Overspending" not in text

    def test_custom_rule_turns_off_a_default_untracked_income_label(self):
        untracked_income.add_rule("Emergency Fund", False, "current", "2026-06")
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 300.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Emergency Fund", 16, 500.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Untracked Income" not in text
        assert "Overspending [200.00] Budget" in text

    def test_rule_scoped_to_a_different_month_does_not_apply(self):
        """make_month_json always sets year_month "2026-06" — a rule scoped
        to a different single month must not leak into this one."""
        untracked_income.add_rule("Other Savings", True, "current", "2026-07")
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 300.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 500.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Untracked Income" not in text


class TestSavingsGrouping:
    """All savings line items should flow through one "Savings" hub node
    (Budget -> Savings -> each line item), the same Budget -> Section ->
    line-item pattern every expense section already uses. A prior version
    had each savings line flow directly out of Budget, which put e.g.
    Emergency Fund visually apart from the rest of the savings cluster
    (2026-07-31 regression)."""

    def test_savings_lines_flow_through_a_savings_hub(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 5000.0)]),
            _section("savings", "Savings", "income_savings", [
                _line_item("Emergency Fund", 16, 500.0),
                _line_item("Managed Brokerages", 19, 1000.0),
            ]),
        ])
        text = to_sankeymatic(month)
        assert "Budget [1500.00] Savings" in text
        assert "Savings [500.00] Emergency Fund" in text
        assert "Savings [1000.00] Managed Brokerages" in text
        # No savings line item flows directly out of Budget anymore.
        assert "Budget [500.00] Emergency Fund" not in text
        assert "Budget [1000.00] Managed Brokerages" not in text

    def test_zero_actual_savings_line_excluded_from_hub_total(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 1000.0)]),
            _section("savings", "Savings", "income_savings", [
                _line_item("Emergency Fund", 16, 500.0),
                _line_item("Other Savings", 21, 0.0),
            ]),
        ])
        text = to_sankeymatic(month)
        assert "Budget [500.00] Savings" in text
        assert "Other Savings" not in text

    def test_no_savings_hub_emitted_when_all_savings_are_zero(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 1000.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Emergency Fund", 16, 0.0)]),
        ])
        text = to_sankeymatic(month)
        # "Underspending" is expected here (income exceeds the zeroed-out
        # outflow) — check specifically for the hub node, not the substring.
        assert "Savings [" not in text
        assert "] Savings" not in text


class TestNodeNameCollisions:
    """Multiple expense sections share the line-item label "Other" (every
    section's catch-all). Sankeymatic identifies nodes by name, so two
    different sections both emitting a flow to a node literally named
    "Other" get merged into one node fed by both parents by d3-sankey —
    visually indistinguishable from a real single category, which read as
    "sections merging together" (2026-07-31 regression)."""

    def test_shared_other_label_gets_disambiguated(self):
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)], other_actual=500.0),
            _section("DAILY LIVING", "Daily Living", "expense", [_line_item("Groceries", 26, 300.0)], other_actual=200.0),
        ])
        text = to_sankeymatic(month)
        assert "Other (Home)" in text
        assert "Other (Daily Living)" in text
        # The bare, unqualified name must not appear as a flow target at all
        # (only ever "Other (...)"), or the collision isn't actually fixed.
        assert "] Other\n" not in text and not text.endswith("] Other")

    def test_unique_labels_are_not_qualified(self):
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
            _section("DAILY LIVING", "Daily Living", "expense", [_line_item("Groceries", 26, 300.0)]),
        ])
        text = to_sankeymatic(month)
        assert "Mortgage (12 Warren)" in text
        assert "Mortgage (12 Warren) (Home)" not in text
        assert "Groceries (Daily Living)" not in text

    def test_other_present_in_only_one_section_is_not_qualified(self):
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)], other_actual=500.0),
            _section("DAILY LIVING", "Daily Living", "expense", [_line_item("Groceries", 26, 300.0)]),  # no Other
        ])
        text = to_sankeymatic(month)
        assert "Home [500.00] Other" in text
        assert "Other (Home)" not in text

    def test_zero_actual_other_does_not_count_as_a_collision(self):
        """An Other line item with $0 actual is never emitted as a flow at
        all (filtered by positive_items) — it shouldn't count toward
        collision detection either."""
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)], other_actual=0.0),
            _section("DAILY LIVING", "Daily Living", "expense", [_line_item("Groceries", 26, 300.0)], other_actual=150.0),
        ])
        text = to_sankeymatic(month)
        assert "Other (Daily Living)" not in text
        assert "Daily Living [150.00] Other" in text


class TestRealisticMonth:
    """A fuller reproduction of the 2026-06 scenario that surfaced both
    bugs at once: four income streams of very different magnitudes, a
    negative net month, and two expense sections both using their Other
    catch-all."""

    def test_full_scenario(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [
                _line_item("Take Home Salary (Zus)", 4, 8873.32),
                _line_item("Take Home Salary (Banneker)", 5, 3698.07),
                _line_item("Interest Income", 6, 0.91),
                _line_item("Apartment Rental Income", 9, 2275.0),
            ]),
            _section("savings", "Savings", "income_savings", [
                _line_item("Other Savings", 21, 1000.0),
            ]),
            _section("HOME", "Home", "expense", [
                _line_item("Mortgage (12 Warren)", 4, 2979.67),
                _line_item("Mortgage + HOA (1 Cityview)", 5, 2241.67),
            ], other_actual=3571.07),
            _section("DAILY LIVING", "Daily Living", "expense", [
                _line_item("Groceries", 26, 760.24),
                _line_item("Dining Out", 27, 1169.78),
            ], other_actual=1199.58),
            _section("TRANSPORTATION", "Transportation", "expense", [
                _line_item("Fuel", 20, 904.69),
            ]),
            _section("HEALTH", "Health", "expense", [
                _line_item("Doctors / Dentist Visits", 43, 2000.0),
            ]),
        ])
        text = to_sankeymatic(month)

        income_total = 8873.32 + 3698.07 + 0.91 + 2275.0
        outflow_total = (
            1000.0 + (2979.67 + 2241.67 + 3571.07) + (760.24 + 1169.78 + 1199.58) + 904.69 + 2000.0
        )
        assert outflow_total > income_total  # sanity check on the fixture itself

        assert "Overspending" in text
        assert ":Overspending #ef4444" in text
        assert "Other (Home)" in text
        assert "Other (Daily Living)" in text
        assert "Take Home Salary (Zus) [8873.32] Budget" in text
        assert "Take Home Salary (Banneker) [3698.07] Budget" in text


class TestGroupByClassification:
    """group_by="classification" replaces the Budget -> Section -> line item
    grouping with Budget -> Needs/Wants -> line item for expense sections —
    Income and Savings are unaffected either way."""

    def test_invalid_group_by_raises(self):
        month = make_month_json([])
        with pytest.raises(ValueError):
            to_sankeymatic(month, group_by="not_a_real_mode")

    def test_default_group_by_is_section(self):
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
        ])
        assert to_sankeymatic(month) == to_sankeymatic(month, group_by="section")

    def test_classification_mode_drops_section_hubs(self):
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
            _section("DAILY LIVING", "Daily Living", "expense", [
                _line_item("Groceries", 26, 500.0),
                _line_item("Dining Out", 27, 300.0),
            ]),
        ])
        text = to_sankeymatic(month, group_by="classification")
        assert "Budget [2000.00] Home" not in text  # no section-hub flow in classification mode
        assert "Budget [2500.00] Needs" in text  # Mortgage + Groceries, both needs
        assert "Budget [300.00] Wants" in text  # Dining Out
        assert "Needs [2000.00] Mortgage (12 Warren)" in text
        assert "Needs [500.00] Groceries" in text
        assert "Wants [300.00] Dining Out" in text

    def test_classification_mode_node_names_still_disambiguated(self):
        """The leaf node's own name/identity is unaffected by group_by —
        "Other" still gets qualified by section when shared, exactly as in
        section mode, so expand/collapse and node-click lookups (which key
        off this same disambiguation in the frontend) keep working."""
        month = make_month_json([
            _section("HOME", "Home", "expense", [], other_actual=100.0),
            _section("DAILY LIVING", "Daily Living", "expense", [], other_actual=50.0),
        ])
        text = to_sankeymatic(month, group_by="classification")
        assert "Other (Home)" in text
        assert "Other (Daily Living)" in text

    def test_classification_mode_unaffected_by_savings_and_income(self):
        month = make_month_json([
            _section("income", "Income", "income_savings", [_line_item("Take Home Salary (Zus)", 4, 5000.0)]),
            _section("savings", "Savings", "income_savings", [_line_item("Other Savings", 21, 500.0)]),
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
        ])
        text = to_sankeymatic(month, group_by="classification")
        assert "Take Home Salary (Zus) [5000.00] Budget" in text
        assert "Budget [500.00] Savings" in text
        assert "Savings [500.00] Other Savings" in text

    def test_classification_mode_respects_custom_overrides(self):
        custom_budget_classification.set_override("HOME", "Mortgage (12 Warren)", "want", False, False)
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
        ])
        text = to_sankeymatic(month, group_by="classification")
        assert "Budget [2000.00] Wants" in text
        assert "Wants [2000.00] Mortgage (12 Warren)" in text
        assert "Budget [2000.00] Needs" not in text  # nothing tagged Need in this fixture

    def test_classification_mode_emits_no_explicit_node_colors(self):
        """An earlier version emitted :Needs/:Wants color directives — those
        made the hub a node-theme-independent explicit color, which then
        couldn't be auto-matched to its own incoming ribbon's color by the
        frontend's applyColors() (SankeyDiagram.tsx), producing a visibly
        clashing seam right at the hub (2026-08-02, user-reported). Needs/
        Wants must fall through to the same hash-derived default every
        other hub uses instead."""
        month = make_month_json([
            _section("HOME", "Home", "expense", [_line_item("Mortgage (12 Warren)", 4, 2000.0)]),
            _section("DAILY LIVING", "Daily Living", "expense", [_line_item("Dining Out", 27, 300.0)]),
        ])
        text = to_sankeymatic(month, group_by="classification")
        assert ":Needs" not in text
        assert ":Wants" not in text
