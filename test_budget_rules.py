"""
Tests for budget_rules.py — the 50/30/20, 28/36, 70/20/10, and 80/20 rule
computations, operating on an already-aggregated month_json (matching
budget_aggregate.aggregate_month_json's shape).

Run with: uv run pytest test_budget_rules.py -v
"""
import pytest

import custom_budget_classification
import untracked_income
from budget_rules import compute_all_rules, compute_buckets


@pytest.fixture(autouse=True)
def isolated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_budget_classification, "CUSTOM_BUDGET_CLASSIFICATION_FILE", tmp_path / "custom_budget_classification.json")
    monkeypatch.setattr(untracked_income, "UNTRACKED_INCOME_FILE", tmp_path / "untracked_income_overrides.json")


def _li(label, actual):
    return {"label": label, "row": 1, "projected": None, "actual": actual, "difference": None, "is_fixed": False, "is_copy_projected": False, "transactions": []}


def _month_json(income=None, savings=None, expenses=None):
    """expenses: {section_key: {label: actual}}"""
    sections = [
        {"key": "income", "label": "Income", "kind": "income_savings", "line_items": [_li(l, a) for l, a in (income or {}).items()]},
        {"key": "savings", "label": "Savings", "kind": "income_savings", "line_items": [_li(l, a) for l, a in (savings or {}).items()]},
    ]
    for section_key, items in (expenses or {}).items():
        sections.append({"key": section_key, "label": section_key, "kind": "expense", "line_items": [_li(l, a) for l, a in items.items()]})
    return {"sections": sections}


class TestComputeBuckets:
    def test_need_want_split(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 5000.0},
            expenses={"DAILY LIVING": {"Groceries": 400.0, "Dining Out": 200.0}},
        )
        buckets = compute_buckets(month_json)
        assert buckets["income"] == 5000.0
        assert buckets["need"] == 400.0
        assert buckets["want"] == 200.0

    def test_mortgage_counts_toward_housing_and_debt(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 5000.0},
            expenses={"HOME": {"Mortgage (12 Warren)": 2000.0}},
        )
        buckets = compute_buckets(month_json)
        assert buckets["housing"] == 2000.0
        assert buckets["debt"] == 2000.0
        assert buckets["need"] == 2000.0

    def test_untracked_income_labels_added_back_to_income(self):
        """Retirement (401k + Match) etc. are payroll-split money never in
        the Income section's own total — compute_buckets must add it back
        to the income denominator, mirroring budget_sankeymatic's own fix
        for the same root cause."""
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 5000.0},
            savings={"Retirement (401k + Match)": 500.0, "Other Savings": 100.0},
        )
        buckets = compute_buckets(month_json)
        assert buckets["income"] == 5500.0
        assert buckets["savings"] == 600.0

    def test_zero_actual_line_items_excluded(self):
        month_json = _month_json(expenses={"DAILY LIVING": {"Groceries": 0.0}})
        buckets = compute_buckets(month_json)
        assert buckets["need"] == 0.0


class TestRules:
    def test_50_30_20_on_target(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 10000.0},
            savings={"Other Savings": 2000.0},
            expenses={
                "DAILY LIVING": {"Groceries": 5000.0},
                "ENTERTAINMENT": {"Streaming / Movies": 3000.0},
            },
        )
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "50_30_20")
        segments = {s["key"]: s for s in rule["segments"]}
        assert segments["need"]["actual_pct"] == 50.0
        assert segments["want"]["actual_pct"] == 30.0
        assert segments["savings"]["actual_pct"] == 20.0
        assert all(s["on_target"] for s in rule["segments"])

    def test_50_30_20_over_target(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 10000.0},
            expenses={"ENTERTAINMENT": {"Streaming / Movies": 5000.0}},
        )
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "50_30_20")
        want_segment = next(s for s in rule["segments"] if s["key"] == "want")
        assert want_segment["actual_pct"] == 50.0
        assert want_segment["on_target"] is False

    def test_28_36_uses_housing_and_debt_only(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 10000.0},
            expenses={
                "HOME": {"Mortgage (12 Warren)": 2500.0},
                "DAILY LIVING": {"Groceries": 1000.0},
            },
        )
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "28_36")
        segments = {s["key"]: s for s in rule["segments"]}
        assert segments["housing"]["actual_pct"] == 25.0
        assert segments["debt"]["actual_pct"] == 25.0
        assert segments["housing"]["on_target"] is True

    def test_70_20_10_debt_not_double_counted_in_spend(self):
        month_json = _month_json(
            income={"Take Home Salary (Zus)": 10000.0},
            savings={"Other Savings": 2000.0},
            expenses={
                "HOME": {"Mortgage (12 Warren)": 3000.0},
                "DAILY LIVING": {"Groceries": 4000.0},
            },
        )
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "70_20_10")
        segments = {s["key"]: s for s in rule["segments"]}
        assert segments["spend"]["actual_amount"] == 4000.0
        assert segments["debt"]["actual_amount"] == 3000.0
        assert segments["savings"]["actual_amount"] == 2000.0

    def test_80_20_only_has_savings_segment(self):
        month_json = _month_json(income={"Take Home Salary (Zus)": 10000.0}, savings={"Other Savings": 1500.0})
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "80_20")
        assert [s["key"] for s in rule["segments"]] == ["savings"]
        assert rule["segments"][0]["actual_pct"] == 15.0
        assert rule["segments"][0]["on_target"] is False

    def test_zero_income_returns_none_percentages(self):
        month_json = _month_json(expenses={"DAILY LIVING": {"Groceries": 100.0}})
        rules = compute_all_rules(month_json)
        rule = next(r for r in rules if r["key"] == "50_30_20")
        need_segment = next(s for s in rule["segments"] if s["key"] == "need")
        assert need_segment["actual_pct"] is None
        assert need_segment["on_target"] is None

    def test_28_36_caveat_present(self):
        rules = compute_all_rules(_month_json())
        rule = next(r for r in rules if r["key"] == "28_36")
        assert rule["caveat"] is not None
        assert "gross" in rule["caveat"].lower()

    def test_all_four_rules_present(self):
        rules = compute_all_rules(_month_json())
        assert {r["key"] for r in rules} == {"50_30_20", "28_36", "70_20_10", "80_20"}
