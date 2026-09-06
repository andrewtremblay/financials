"""
budget_sankeymatic.py — Sankeymatic-format text generator for the web
dashboard, built directly from budget_aggregate.aggregate_month_json's
already-resolved totals.

Deliberately does NOT reuse utils.fmt_sankeymatic/count_categories: those
were built for the PDF/manual-analysis pipeline and use utils.IGNORE_CATEGORY,
which disagrees with sheet_category_map.IGNORE_CATEGORIES (e.g. utils
ignores INTEREST, which sheet_category_map treats as real income). Reusing
them here would produce a diagram whose numbers don't reconcile with the
dashboard's own Income section. This generator works from month_json
instead, which already uses the correct (sheet_category_map) rules — the
same ones driving every other part of the dashboard — so the two always
agree.
"""

import budget_classification
import untracked_income

GROUP_BY_OPTIONS = ("section", "classification")


def to_sankeymatic(month_json: dict, group_by: str = "section") -> str:
    """
    group_by:
      - "section" (default): Budget -> expense Section -> line item, the
        original grouping.
      - "classification": Budget -> Needs/Wants -> line item instead — drops
        the section hubs (HOME, DAILY LIVING, ...) in favor of
        budget_classification.py's Need/Want tag per line item, so the
        diagram lines up visually with the Budget Rules tab's 50/30/20
        breakdown (2026-08-02, user-specified: "have these wants / needs /
        savings optionally displayed on a sankeymatic"). The Savings hub is
        unchanged either way — it's already that same three-way split's
        "savings" bucket.
    """
    if group_by not in GROUP_BY_OPTIONS:
        raise ValueError(f"unknown group_by {group_by!r}; must be one of {GROUP_BY_OPTIONS}")

    # Anchors untracked_income.is_untracked_income's date-scoped rule
    # resolution (see that module) — a single month_json has "year_month";
    # a range_json has "year_months" (the range's own months in order), for
    # which the LAST/most-recent month is used, matching how every other
    # month-anchored concept in this app (e.g. "YTD") resolves against a
    # range's end rather than its start.
    anchor_year_month = month_json.get("year_month") or (month_json.get("year_months") or [None])[-1]

    lines: list[str] = []
    income_total = 0.0
    total_outflow = 0.0  # expenses AND savings — both leave Budget
    classification_totals = {"Needs": 0.0, "Wants": 0.0}
    classification_lines: list[str] = []

    # Several expense sections share a line-item label ("Other" appears
    # under HOME, DAILY LIVING, ENTERTAINMENT, and VACATION/HOLIDAY).
    # Sankeymatic identifies nodes by name, so two different sections both
    # emitting a flow to a node literally named "Other" get merged by
    # d3-sankey into one node fed by both parents — visually indistinguishable
    # from a real single category (2026-07-31 fix: this is what looked like
    # "sections merging"). Qualify any label used by more than one section —
    # unaffected by group_by, since this is about a leaf node's own name,
    # not which hub feeds it.
    label_to_sections: dict[str, set[str]] = {}
    for section in month_json["sections"]:
        if section["kind"] != "expense":
            continue
        line_items = list(section["line_items"])
        if section.get("other"):
            line_items.append(section["other"])
        for li in line_items:
            if li["actual"] > 0:
                label_to_sections.setdefault(li["label"], set()).add(section["label"])
    shared_labels = {label for label, sections in label_to_sections.items() if len(sections) > 1}

    def node_name(section_label: str, item_label: str) -> str:
        return f"{item_label} ({section_label})" if item_label in shared_labels else item_label

    for section in month_json["sections"]:
        if section["kind"] == "income_savings":
            if section["key"] == "income":
                for li in section["line_items"]:
                    amount = li["actual"]
                    if amount <= 0:
                        continue
                    lines.append(f'{li["label"]} [{amount:.2f}] Budget')
                    income_total += amount
            else:
                # Savings: Budget -> Savings -> each line item, the same
                # Budget -> Section -> line-item pattern every expense
                # section uses — previously each savings line flowed
                # directly out of Budget, which put e.g. Emergency Fund
                # visually apart from the rest of the savings cluster
                # (2026-07-31, user-specified: group all savings under one node).
                positive_items = [li for li in section["line_items"] if li["actual"] > 0]
                savings_total = sum(li["actual"] for li in positive_items)
                if savings_total > 0:
                    lines.append(f'Budget [{savings_total:.2f}] Savings')
                    total_outflow += savings_total  # leaves Budget, counts toward the balance check below
                    for li in positive_items:
                        lines.append(f'Savings [{li["actual"]:.2f}] {li["label"]}')
                        if untracked_income.is_untracked_income(li["label"], anchor_year_month):
                            lines.append(f'Untracked Income [{li["actual"]:.2f}] Budget')
                            income_total += li["actual"]
            continue

        # expense section
        line_items = list(section["line_items"])
        if section.get("other"):
            line_items.append(section["other"])
        positive_items = [li for li in line_items if li["actual"] > 0]
        section_total = sum(li["actual"] for li in positive_items)
        if section_total <= 0:
            continue
        total_outflow += section_total

        if group_by == "section":
            lines.append(f'Budget [{section_total:.2f}] {section["label"]}')
            for li in positive_items:
                lines.append(f'{section["label"]} [{li["actual"]:.2f}] {node_name(section["label"], li["label"])}')
        else:
            for li in positive_items:
                tag = budget_classification.classify_line_item(section["key"], li["label"])
                hub = "Needs" if tag["budget_type"] == "need" else "Wants"
                classification_totals[hub] += li["actual"]
                classification_lines.append(f'{hub} [{li["actual"]:.2f}] {node_name(section["label"], li["label"])}')

    if group_by == "classification":
        # No explicit :Needs/:Wants color directive here (an earlier version
        # of this had one) — an explicit node color always wins over the
        # frontend's "match this node's color to its single incoming
        # ribbon" fix (SankeyDiagram.tsx's applyColors), so it left the
        # Needs/Wants hub as a visibly different, clashing shade next to its
        # own incoming Budget-colored ribbon (2026-08-02, user-reported: an
        # "odd vertical line" right at the hub). Left to the same
        # hash-derived default every other hub uses, it gets auto-matched
        # to its ribbon instead, like Savings/Home/every other hub already
        # correctly is.
        for hub in ("Needs", "Wants"):
            if classification_totals[hub] > 0:
                lines.append(f'Budget [{classification_totals[hub]:.2f}] {hub}')
        lines.extend(classification_lines)

    lines.append("")
    # Balance Budget's total inflow (income) against total OUTFLOW (expenses
    # + savings — a prior version compared income against expenses only,
    # silently ignoring that savings amounts also leave Budget; any month
    # where spending+saving exceeded income rendered an unbalanced node with
    # a visible gap between the income ribbons and the rest of the Budget
    # block, 2026-07-31 fix). untracked_income.is_untracked_income above
    # already keeps money that was never real take-home income (pre-tax
    # deductions, payroll-split savings) from artificially inflating this
    # gap — what's left here is genuine surplus or deficit against income
    # that was actually available to spend.
    #
    # A tiny epsilon (a cent) absorbs float-summation drift across however
    # many transactions fed into these totals, so a true break-even month
    # doesn't spuriously render a $0.00 (or $0.01) Overspending/Underspending
    # sliver — emitted only when the gap is large enough to be real
    # (2026-08-01, user-specified: "if it's a perfect break even, don't show
    # it"). Emitted last (after every section), so in the diagram's rightmost
    # column it lands below/after the expense nodes, not mixed in with them
    # (2026-08-01, user-specified: "an underspending node under the
    # expenses").
    gap = income_total - total_outflow
    if gap > 0.01:
        lines.append(f'Budget [{gap:.2f}] Underspending')
    elif gap < -0.01:
        lines.append(f'Overspending [{-gap:.2f}] Budget')
        # Flag it red, the same way the dashboard already colors over-budget
        # line items — an overspending month should read as a warning, not
        # blend in with the rest of the income-side flows.
        lines.append(':Overspending #ef4444')

    return "\n".join(lines)
