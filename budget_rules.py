"""
budget_rules.py — common personal-finance ratio rules (50/30/20, 28/36,
70/20/10, 80/20 pay-yourself-first) computed from an already-aggregated
month/range JSON (aggregate_month_json/aggregate_range_json's output) plus
each line item's Need/Want/Housing/Debt tag (budget_classification.py).

Income basis: take-home income as aggregated (Plaid never sees gross/
pre-tax pay) — every rule that conventionally uses gross income (28/36) is
therefore a net-income approximation, not the number a mortgage lender would
compute (2026-08-02, user-specified after discussing the tradeoff; surfaced
via that rule's `caveat` field for the UI to show).

Reuses untracked_income.is_untracked_income for the same reason
budget_sankeymatic.py does: some Savings-section line items (Retirement,
Emergency Fund, Managed Brokerages, by default — user-configurable, see
untracked_income.py) are payroll-split money that never appears in the
Income section's total to begin with — without adding it back to the income
denominator here too, every rule below would understate the true savings
rate by exactly the amount budget_sankeymatic already corrects for on the
diagram side.
"""

from dataclasses import dataclass
from typing import Callable

import budget_classification
import untracked_income


def _expense_line_items(month_json: dict):
    """Yields (section_key, label, actual) for every positive expense-section
    line item, including each section's "Other" catch-all."""
    for section in month_json["sections"]:
        if section["kind"] != "expense":
            continue
        items = list(section["line_items"])
        if section.get("other"):
            items.append(section["other"])
        for li in items:
            if li["actual"] > 0:
                yield section["key"], li["label"], li["actual"]


def compute_buckets(month_json: dict) -> dict[str, float]:
    """{income, need, want, savings, housing, debt} — the raw dollar totals
    every rule below is a ratio of."""
    # Same anchor-resolution rule as budget_sankeymatic.to_sankeymatic: a
    # single month_json has "year_month"; a range_json has "year_months",
    # for which the last/most-recent month is used.
    anchor_year_month = month_json.get("year_month") or (month_json.get("year_months") or [None])[-1]

    income = 0.0
    savings = 0.0
    for section in month_json["sections"]:
        if section["kind"] != "income_savings":
            continue
        for li in section["line_items"]:
            if li["actual"] <= 0:
                continue
            if section["key"] == "income":
                income += li["actual"]
            else:
                savings += li["actual"]
                if untracked_income.is_untracked_income(li["label"], anchor_year_month):
                    income += li["actual"]

    need = want = housing = debt = 0.0
    for section_key, label, actual in _expense_line_items(month_json):
        tag = budget_classification.classify_line_item(section_key, label)
        if tag["budget_type"] == "need":
            need += actual
        else:
            want += actual
        if tag["housing"]:
            housing += actual
        if tag["debt"]:
            debt += actual

    return {"income": income, "need": need, "want": want, "savings": savings, "housing": housing, "debt": debt}


def _pct(amount: float, income: float) -> float | None:
    return round(amount / income * 100, 1) if income > 0 else None


@dataclass
class Segment:
    key: str
    label: str
    actual_amount: float
    actual_pct: float | None
    target_pct: float
    # Savings-type segments want actual_pct >= target_pct ("at_or_over");
    # every spend-type segment (need/want/housing/debt) wants the opposite.
    good_direction: str  # "at_or_under" | "at_or_over"

    @property
    def on_target(self) -> bool | None:
        if self.actual_pct is None:
            return None
        return self.actual_pct <= self.target_pct if self.good_direction == "at_or_under" else self.actual_pct >= self.target_pct


def _segment(key: str, label: str, amount: float, income: float, target_pct: float, good_direction: str) -> Segment:
    return Segment(key, label, round(amount, 2), _pct(amount, income), target_pct, good_direction)


def _rule_50_30_20(b: dict) -> list[Segment]:
    return [
        _segment("need", "Needs", b["need"], b["income"], 50, "at_or_under"),
        _segment("want", "Wants", b["want"], b["income"], 30, "at_or_under"),
        _segment("savings", "Savings", b["savings"], b["income"], 20, "at_or_over"),
    ]


def _rule_28_36(b: dict) -> list[Segment]:
    return [
        _segment("housing", "Housing costs", b["housing"], b["income"], 28, "at_or_under"),
        _segment("debt", "Total debt payments", b["debt"], b["income"], 36, "at_or_under"),
    ]


def _rule_70_20_10(b: dict) -> list[Segment]:
    # Non-overlapping buckets: "spend" is every need/want dollar not already
    # counted as debt, so e.g. a mortgage payment (need + debt) isn't
    # double-counted across the spend and debt segments.
    spend = b["need"] + b["want"] - b["debt"]
    return [
        _segment("spend", "Living expenses", spend, b["income"], 70, "at_or_under"),
        _segment("savings", "Savings", b["savings"], b["income"], 20, "at_or_over"),
        _segment("debt", "Debt repayment", b["debt"], b["income"], 10, "at_or_under"),
    ]


def _rule_80_20(b: dict) -> list[Segment]:
    return [
        _segment("savings", "Savings", b["savings"], b["income"], 20, "at_or_over"),
    ]


@dataclass
class Rule:
    key: str
    label: str
    description: str
    compute: Callable[[dict], list[Segment]]
    caveat: str | None = None


RULES: tuple[Rule, ...] = (
    Rule(
        "50_30_20", "50/30/20",
        "50% of income to needs, 30% to wants, 20% to savings.",
        _rule_50_30_20,
    ),
    Rule(
        "28_36", "28/36",
        "Housing costs at or under 28% of income, total debt payments at or under 36%.",
        _rule_28_36,
        caveat=(
            "Conventionally computed against gross (pre-tax) income; this app only sees take-home "
            "deposits, so this is a net-income approximation and will read more conservatively than "
            "a lender's calculation. “Debt” is also limited to whatever's tagged as debt in "
            "Budget Classification (currently just mortgage payments) — a car loan or other debt "
            "with no tracked line item won't be counted."
        ),
    ),
    Rule(
        "70_20_10", "70/20/10",
        "70% of income to living expenses, 20% to savings, 10% to debt repayment.",
        _rule_70_20_10,
    ),
    Rule(
        "80_20", "80/20 (pay yourself first)",
        "At least 20% of income straight to savings; no constraint on the rest.",
        _rule_80_20,
    ),
)


def compute_all_rules(month_json: dict) -> list[dict]:
    buckets = compute_buckets(month_json)
    return [
        {
            "key": rule.key,
            "label": rule.label,
            "description": rule.description,
            "caveat": rule.caveat,
            "income": round(buckets["income"], 2),
            "segments": [
                {
                    "key": seg.key,
                    "label": seg.label,
                    "actual_amount": seg.actual_amount,
                    "actual_pct": seg.actual_pct,
                    "target_pct": seg.target_pct,
                    "on_target": seg.on_target,
                }
                for seg in rule.compute(buckets)
            ],
        }
        for rule in RULES
    ]
