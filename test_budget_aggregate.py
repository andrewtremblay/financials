"""
Tests for budget_aggregate.py — the shared category-resolution core used by
both sheets_sync.aggregate_month (Google Sheet) and the web API's
aggregate_month_json.

Run with: uv run pytest test_budget_aggregate.py -v
"""
import pandas as pd
import pytest

import budget_schema
import custom_categories
import overrides
from budget_aggregate import _ignored_transactions_for_month, _resolve_month, aggregate_month_json, aggregate_range_json, compute_range_months


@pytest.fixture(autouse=True)
def isolated_overrides_file(tmp_path, monkeypatch):
    """_ignored_transactions_for_month reads overrides.py for notes — never
    touch the real category_overrides.json."""
    monkeypatch.setattr(overrides, "OVERRIDES_FILE", tmp_path / "category_overrides.json")


def txn(date, description, amount, category, year_month=None, account="Test Bank checking 0000", transaction_id=None):
    return {
        "raw_transaction": str([date, description, amount]),
        "description": description,
        "date": date,
        "amount": amount,
        "category": category,
        "transaction_id": transaction_id,
        "year_month": year_month or date[:7],
        "account": account,
    }


COLUMNS = ["raw_transaction", "description", "date", "amount", "category", "transaction_id", "year_month", "account"]


def make_df(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


class TestResolveMonthBasics:
    def test_simple_income_and_expense_mapping(self):
        df = make_df([
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "Stop & Shop", 100.0, "GROCERY"),
        ])
        totals, txns, needs_review = _resolve_month(df, "2026-06")
        assert totals[("income", "Take Home Salary (Zus)")] == 5000.0
        assert totals[("DAILY LIVING", "Groceries")] == 100.0
        assert needs_review == {}
        assert len(txns[("income", "Take Home Salary (Zus)")]) == 1

    def test_filters_to_requested_month_only(self):
        df = make_df([
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-07-01", "Employer Inc", 5000.0, "WAGES"),
        ])
        totals, _, _ = _resolve_month(df, "2026-06")
        assert totals[("income", "Take Home Salary (Zus)")] == 5000.0

    def test_ignore_categories_excluded_entirely(self):
        df = make_df([
            txn("2026-06-01", "Transfer to Savings", 500.0, "BANK_TRANSFER"),
        ])
        totals, txns, needs_review = _resolve_month(df, "2026-06")
        assert totals == {}
        assert needs_review == {}


class TestNeedsReview:
    def test_needs_review_category_excluded_from_totals(self):
        df = make_df([
            txn("2026-06-01", "Some Insurer", 200.0, "INSURANCE"),
        ])
        totals, _, needs_review = _resolve_month(df, "2026-06")
        assert totals == {}
        assert "INSURANCE" in needs_review
        assert needs_review["INSURANCE"][0]["amount"] == 200.0

    def test_unmapped_category_goes_to_unmapped_bucket(self):
        df = make_df([
            txn("2026-06-01", "Mystery Charge", 50.0, "SOME_BRAND_NEW_CATEGORY"),
        ])
        totals, _, needs_review = _resolve_month(df, "2026-06")
        assert totals == {}
        assert "UNMAPPED:SOME_BRAND_NEW_CATEGORY" in needs_review


class TestUtilitiesSplit:
    def test_national_grid_splits_50_50(self):
        df = make_df([
            txn("2026-06-01", "National Grid", 200.0, "UTILITIES"),
        ])
        totals, txns, _ = _resolve_month(df, "2026-06")
        assert totals[("HOME", "Electricity (Nat'l grid)")] == 100.0
        assert totals[("HOME", "Gas (Nat'l grid)")] == 100.0
        assert "1/2 of $200.00 bill" in txns[("HOME", "Electricity (Nat'l grid)")][0]["description"]

    def test_non_national_grid_utility_goes_to_home_other(self):
        df = make_df([
            txn("2026-06-01", "PPL Electric", 30.0, "UTILITIES"),
        ])
        totals, _, _ = _resolve_month(df, "2026-06")
        assert totals[("HOME", "Other")] == 30.0
        assert ("HOME", "Electricity (Nat'l grid)") not in totals


class TestHierarchicalFallback:
    def test_subcategory_preferred_over_parent(self):
        """FOOD GROCERIES must resolve to Groceries via the GROCERIES
        subcategory, not fall through to the FOOD parent -> Dining Out
        (2026-07-29 regression: Stop & Shop/Target/Walmart)."""
        df = make_df([
            txn("2026-06-01", "Stop & Shop", 80.0, "FOOD GROCERIES"),
        ])
        totals, _, _ = _resolve_month(df, "2026-06")
        assert totals[("DAILY LIVING", "Groceries")] == 80.0
        assert ("DAILY LIVING", "Dining Out") not in totals

    def test_parent_fallback_when_subcategory_unmapped(self):
        """FOOD RESTAURANTS has no direct "RESTAURANTS" mapping (only
        "RESTAURANT" singular), so it falls back to the FOOD parent."""
        df = make_df([
            txn("2026-06-01", "Some Diner", 25.0, "FOOD RESTAURANTS"),
        ])
        totals, _, _ = _resolve_month(df, "2026-06")
        assert totals[("DAILY LIVING", "Dining Out")] == 25.0


class TestZusBrokerageNetting:
    def test_managed_brokerages_not_netted_out_of_zus_salary(self):
        """Managed Brokerages' transfer is its own distinct payroll-run
        deposit, never combined with the main paycheck deposit Plaid sees —
        so Take Home Salary (Zus)'s raw WAGES total already excludes it and
        must not be further reduced (2026-08-02, user-specified: an earlier
        netting step here double-subtracted money that was never counted in
        the first place)."""
        df = make_df([
            txn("2026-06-01", "Paycheck", 5000.0, "WAGES"),
            txn("2026-06-02", "Funds Transfer to Brokerage", 500.0, "MANAGED_BROKERAGES"),
        ])
        totals, txns, _ = _resolve_month(df, "2026-06")
        assert totals[("income", "Take Home Salary (Zus)")] == 5000.0
        assert totals[("savings", "Managed Brokerages")] == 500.0
        notes = [t["description"] for t in txns[("income", "Take Home Salary (Zus)")]]
        assert not any("auto-transferred to Managed Brokerages" in n for n in notes)


class TestAggregateMonthJson:
    def test_fixed_value_line_item_ignores_plaid_and_projected(self):
        df = make_df([])
        result = aggregate_month_json(df, "2026-06", projected={("income", "Apartment Rental Income"): 0.0})
        income_section = next(s for s in result["sections"] if s["key"] == "income")
        rental = next(li for li in income_section["line_items"] if li["label"] == "Apartment Rental Income")
        assert rental["actual"] == 2275.00
        assert rental["is_fixed"] is True
        assert rental["transactions"] == []

    def test_copy_projected_line_item_mirrors_projected(self):
        df = make_df([
            # Real Plaid data exists for this category too, but must be
            # ignored in favor of the projected value (2026-07-29 fix).
            txn("2026-06-01", "Paycheck split", 250.0, "EMERGENCY_FUND_ZUS"),
        ])
        result = aggregate_month_json(df, "2026-06", projected={("savings", "Emergency Fund"): 500.0})
        savings_section = next(s for s in result["sections"] if s["key"] == "savings")
        emergency = next(li for li in savings_section["line_items"] if li["label"] == "Emergency Fund")
        assert emergency["actual"] == 500.0
        assert emergency["is_copy_projected"] is True

    def test_copy_projected_defaults_to_zero_without_projected_data(self):
        df = make_df([])
        result = aggregate_month_json(df, "2026-06", projected=None)
        savings_section = next(s for s in result["sections"] if s["key"] == "savings")
        emergency = next(li for li in savings_section["line_items"] if li["label"] == "Emergency Fund")
        assert emergency["actual"] == 0.0
        assert emergency["projected"] is None
        assert emergency["difference"] is None

    def test_needs_review_includes_full_transaction_detail(self):
        df = make_df([
            txn("2026-06-01", "Some Insurer", 200.0, "INSURANCE", transaction_id="txn-abc"),
        ])
        result = aggregate_month_json(df, "2026-06")
        bucket = next(b for b in result["needs_review"] if b["category"] == "INSURANCE")
        assert bucket["amount"] == 200.0
        assert bucket["count"] == 1
        assert bucket["transactions"][0]["transaction_id"] == "txn-abc"

    def test_regular_line_item_shows_real_transactions(self):
        df = make_df([
            txn("2026-06-01", "Stop & Shop", 80.0, "GROCERY", transaction_id="txn-1"),
        ])
        result = aggregate_month_json(df, "2026-06")
        daily_living = next(s for s in result["sections"] if s["key"] == "DAILY LIVING")
        groceries = next(li for li in daily_living["line_items"] if li["label"] == "Groceries")
        assert groceries["actual"] == 80.0
        assert len(groceries["transactions"]) == 1
        assert groceries["transactions"][0]["transaction_id"] == "txn-1"

    def test_all_sections_present_even_when_empty(self):
        df = make_df([])
        result = aggregate_month_json(df, "2026-06")
        assert {s["key"] for s in result["sections"]} == {s.key for s in budget_schema.BUDGET_SECTIONS}


class TestCustomCategories:
    """A category created through the "add a new category" UI (see
    custom_categories.py, api_server.POST /api/categories) is persisted
    outside sheet_category_map.CATEGORY_TO_LINE_ITEM — _resolve_month must
    merge it in, otherwise a transaction assigned that category falls
    straight into UNMAPPED needs_review, defeating the point of letting the
    user pick a real section/subcategory for it (2026-08-01 regression,
    caught via a live Playwright run: /api/categories knew about the new
    category, but aggregation never consulted the same store)."""

    def test_custom_category_resolves_to_its_chosen_line_item(self, monkeypatch, tmp_path):
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")
        custom_categories.add_custom_category("CONCERT TICKETS", "ENTERTAINMENT", "Concerts / Plays")
        df = make_df([
            txn("2026-06-01", "Ticketmaster", 75.0, "CONCERT TICKETS", transaction_id="txn-concert"),
        ])
        totals, txns, needs_review = _resolve_month(df, "2026-06")
        assert totals[("ENTERTAINMENT", "Concerts / Plays")] == 75.0
        assert needs_review == {}

    def test_unknown_category_without_custom_entry_still_goes_unmapped(self, monkeypatch, tmp_path):
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")
        df = make_df([
            txn("2026-06-01", "Mystery", 10.0, "NEVER_ADDED_CATEGORY"),
        ])
        _, _, needs_review = _resolve_month(df, "2026-06")
        assert "UNMAPPED:NEVER_ADDED_CATEGORY" in needs_review


class TestStrayLineItemMapping:
    """A category can map (via sheet_category_map.CATEGORY_TO_LINE_ITEM, or
    its runtime custom_categories.py extension used by the "add a new
    category" UI — see api_server.POST /api/categories) to a (section,
    line_item) pair that isn't one of that section's fixed rows in
    budget_schema.BUDGET_SECTIONS, e.g. a brand-new subcategory with no
    corresponding Google Sheet row yet. This is always a custom category in
    practice — CATEGORY_TO_LINE_ITEM's own static entries always point at a
    real schema LineItem.

    Before the 2026-08-01 fix this either silently dropped the money (it
    *did* resolve to a mapping, so _resolve_month never flagged it as
    unmapped, but aggregate_month_json's line item lookup only ever matched
    known LineItem labels or the literal "Other" bucket), or — in a
    once-fixed intermediate version — folded it into the section's generic
    "Other" bucket, erasing the distinct name the user just chose, and for
    sections with no "Other" row at all (Savings, Transportation, Health)
    left it stuck in needs_review forever with no path to ever showing up
    anywhere else. It must now get its own real, distinctly-named line item
    in its section, every time, regardless of whether that section happens
    to have an "Other" row."""

    def test_unknown_line_item_gets_its_own_named_entry(self, monkeypatch):
        import sheet_category_map

        monkeypatch.setitem(sheet_category_map.CATEGORY_TO_LINE_ITEM, "PET_CARE", ("DAILY LIVING", "Pet Supplies"))
        df = make_df([
            txn("2026-06-01", "Petco", 40.0, "PET_CARE", transaction_id="txn-pet"),
        ])
        result = aggregate_month_json(df, "2026-06")
        daily_living = next(s for s in result["sections"] if s["key"] == "DAILY LIVING")
        pet_supplies = next(li for li in daily_living["line_items"] if li["label"] == "Pet Supplies")
        assert pet_supplies["actual"] == 40.0
        assert pet_supplies["transactions"][0]["transaction_id"] == "txn-pet"
        # DAILY LIVING's real "Other" bucket is untouched by this — it's a
        # distinct line item, not folded in.
        assert daily_living["other"]["actual"] == 0.0
        assert result["needs_review"] == []

    def test_unknown_line_item_in_section_without_other_still_gets_its_own_entry(self, monkeypatch):
        import sheet_category_map

        # TRANSPORTATION has no other_row (see budget_schema.py) — this is
        # exactly the shape that shipped broken: a custom Savings category
        # (also no other_row) stuck a real recategorized transaction in
        # needs_review forever, invisible in the sidebar and diagram.
        monkeypatch.setitem(sheet_category_map.CATEGORY_TO_LINE_ITEM, "RIDESHARE", ("TRANSPORTATION", "Rideshare"))
        df = make_df([
            txn("2026-06-01", "Uber", 20.0, "RIDESHARE", transaction_id="txn-uber"),
        ])
        result = aggregate_month_json(df, "2026-06")
        transportation = next(s for s in result["sections"] if s["key"] == "TRANSPORTATION")
        rideshare = next(li for li in transportation["line_items"] if li["label"] == "Rideshare")
        assert rideshare["actual"] == 20.0
        assert rideshare["transactions"][0]["transaction_id"] == "txn-uber"
        assert result["needs_review"] == []


class TestComputeRangeMonths:
    """compute_range_months drives the dashboard's 1M/3M/6M/1Y/YTD lookback
    picker -- it decides which year_months feed aggregate_range_json."""

    def test_3m_returns_three_most_recent_available_months(self):
        available = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
        assert compute_range_months(available, "3M", "2026-05") == ["2026-03", "2026-04", "2026-05"]

    def test_3m_anchored_mid_history(self):
        available = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
        assert compute_range_months(available, "3M", "2026-03") == ["2026-01", "2026-02", "2026-03"]

    def test_short_range_when_not_enough_history(self):
        available = ["2026-04", "2026-05"]
        assert compute_range_months(available, "6M", "2026-05") == ["2026-04", "2026-05"]

    def test_1m_returns_just_the_anchor(self):
        available = ["2026-04", "2026-05"]
        assert compute_range_months(available, "1M", "2026-05") == ["2026-05"]

    def test_skips_gaps_rather_than_padding_a_zero_month(self):
        """A month with zero synced Plaid activity is simply absent from
        `available_months` -- 3M must still return 3 months of *real* data,
        not 3 calendar months back with a phantom gap month silently
        included."""
        available = ["2026-01", "2026-03", "2026-04", "2026-05"]  # no 2026-02 data
        assert compute_range_months(available, "3M", "2026-05") == ["2026-03", "2026-04", "2026-05"]

    def test_ytd_returns_january_through_anchor_in_anchors_year(self):
        available = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
        assert compute_range_months(available, "YTD", "2026-03") == ["2026-01", "2026-02", "2026-03"]

    def test_ytd_excludes_prior_year_even_if_available(self):
        available = ["2025-06", "2026-01"]
        assert compute_range_months(available, "YTD", "2026-01") == ["2026-01"]

    def test_ytd_skips_gap_months_within_the_year(self):
        available = ["2026-01", "2026-03"]  # no Feb data
        assert compute_range_months(available, "YTD", "2026-03") == ["2026-01", "2026-03"]

    def test_unknown_range_key_raises(self):
        with pytest.raises(ValueError):
            compute_range_months(["2026-01"], "2Y", "2026-01")

    def test_anchor_not_in_available_months_raises(self):
        with pytest.raises(ValueError):
            compute_range_months(["2026-01"], "3M", "2026-06")


class TestAggregateRangeJson:
    def test_sums_actuals_across_months(self):
        df = make_df([
            txn("2026-05-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-05-02", "Stop & Shop", 100.0, "GROCERY"),
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "Stop & Shop", 150.0, "GROCERY"),
        ])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        income = next(s for s in result["sections"] if s["key"] == "income")
        zus = next(li for li in income["line_items"] if li["label"] == "Take Home Salary (Zus)")
        assert zus["actual"] == 10000.0
        daily_living = next(s for s in result["sections"] if s["key"] == "DAILY LIVING")
        groceries = next(li for li in daily_living["line_items"] if li["label"] == "Groceries")
        assert groceries["actual"] == 250.0
        assert len(groceries["transactions"]) == 2
        assert result["year_months"] == ["2026-05", "2026-06"]

    def test_fixed_value_line_item_scales_with_month_count(self):
        """Apartment Rental Income is a fixed $2275/month constant -- across
        a 2-month range that should sum to $4550, not stay pinned at a
        single month's $2275."""
        df = make_df([])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        income = next(s for s in result["sections"] if s["key"] == "income")
        rental = next(li for li in income["line_items"] if li["label"] == "Apartment Rental Income")
        assert rental["actual"] == 2275.00 * 2
        assert rental["is_fixed"] is True

    def test_projected_sums_across_months_with_sheet_tabs(self):
        df = make_df([])
        result = aggregate_range_json(
            df, ["2026-05", "2026-06"],
            projected_by_month={
                "2026-05": {("savings", "Emergency Fund"): 500.0},
                "2026-06": {("savings", "Emergency Fund"): 300.0},
            },
        )
        savings = next(s for s in result["sections"] if s["key"] == "savings")
        emergency = next(li for li in savings["line_items"] if li["label"] == "Emergency Fund")
        assert emergency["projected"] == 800.0
        assert emergency["actual"] == 800.0  # copy_projected mirrors PROJECTED per month
        assert emergency["difference"] == 0.0

    def test_projected_treats_missing_month_sheet_tab_as_zero_contribution(self):
        """One month in the range has no Google Sheet tab at all
        (projected=None for that month) -- its contribution to the range's
        summed PROJECTED is $0, not "the whole range's PROJECTED becomes
        unavailable" (that's reserved for when *no* month in the range has
        a tab)."""
        df = make_df([])
        result = aggregate_range_json(
            df, ["2026-05", "2026-06"],
            projected_by_month={"2026-05": {("HOME", "Mortgage (12 Warren)"): 3000.0}, "2026-06": None},
        )
        home = next(s for s in result["sections"] if s["key"] == "HOME")
        mortgage = next(li for li in home["line_items"] if li["label"] == "Mortgage (12 Warren)")
        assert mortgage["projected"] == 3000.0

    def test_projected_is_none_when_no_month_has_a_sheet_tab(self):
        df = make_df([])
        result = aggregate_range_json(df, ["2026-05", "2026-06"], projected_by_month=None)
        savings = next(s for s in result["sections"] if s["key"] == "savings")
        emergency = next(li for li in savings["line_items"] if li["label"] == "Emergency Fund")
        assert emergency["projected"] is None
        assert emergency["difference"] is None

    def test_needs_review_unioned_across_months(self):
        df = make_df([
            txn("2026-05-01", "Some Insurer", 200.0, "INSURANCE", transaction_id="txn-a"),
            txn("2026-06-01", "Some Insurer", 250.0, "INSURANCE", transaction_id="txn-b"),
        ])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        bucket = next(b for b in result["needs_review"] if b["category"] == "INSURANCE")
        assert bucket["amount"] == 450.0
        assert bucket["count"] == 2
        ids = {t["transaction_id"] for t in bucket["transactions"]}
        assert ids == {"txn-a", "txn-b"}

    def test_empty_year_months_raises(self):
        df = make_df([])
        with pytest.raises(ValueError):
            aggregate_range_json(df, [])

    def test_single_month_range_matches_aggregate_month_json(self):
        """A degenerate 1-month range should reproduce aggregate_month_json's
        own numbers exactly (modulo the year_month/year_months key)."""
        df = make_df([txn("2026-06-01", "Stop & Shop", 80.0, "GROCERY")])
        single = aggregate_month_json(df, "2026-06")
        ranged = aggregate_range_json(df, ["2026-06"])
        assert ranged["year_months"] == ["2026-06"]

        def groceries_actual(result):
            return next(
                li for s in result["sections"] if s["key"] == "DAILY LIVING"
                for li in s["line_items"] if li["label"] == "Groceries"
            )["actual"]

        assert groceries_actual(single) == groceries_actual(ranged) == 80.0

    def test_stray_line_item_present_in_only_one_month_is_not_dropped(self, monkeypatch, tmp_path):
        """A custom category's synthesized line item (see
        TestStrayLineItemMapping above) only appears in aggregate_month_json's
        output for months where it actually had a transaction — the range
        merge used to match per-month line_items lists by fixed index
        position, which silently dropped/misaligned any entry that wasn't
        present in every single month (2026-08-02 regression, found while
        adding custom top-level sections). A custom category with activity
        in only ONE month of a 2-month range must still show up, with the
        correct (not double-counted, not zeroed) total."""
        monkeypatch.setattr(custom_categories, "CUSTOM_CATEGORIES_FILE", tmp_path / "custom_categories.json")
        custom_categories.add_custom_category("CONCERT TICKETS", "ENTERTAINMENT", "Concerts / Plays")
        df = make_df([
            txn("2026-05-01", "Ticketmaster", 75.0, "CONCERT TICKETS", transaction_id="txn-concert"),
            # June has no CONCERT TICKETS activity at all -- that month's
            # aggregate_month_json output has no synthetic entry for it.
            txn("2026-06-01", "Stop & Shop", 50.0, "GROCERY"),
        ])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        entertainment = next(s for s in result["sections"] if s["key"] == "ENTERTAINMENT")
        concerts = next(li for li in entertainment["line_items"] if li["label"] == "Concerts / Plays")
        assert concerts["actual"] == 75.0
        assert len(concerts["transactions"]) == 1
        assert concerts["transactions"][0]["transaction_id"] == "txn-concert"

    def test_hidden_unioned_across_months(self):
        df = make_df([
            txn("2026-05-01", "Payment - Thank You", 200.0, "CREDIT_CARD_PAYMENT", transaction_id="txn-a"),
            txn("2026-06-01", "Payment - Thank You", 250.0, "CREDIT_CARD_PAYMENT", transaction_id="txn-b"),
        ])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        bucket = next(b for b in result["hidden"] if b["category"] == "CREDIT_CARD_PAYMENT")
        assert bucket["amount"] == 450.0
        assert bucket["count"] == 2
        ids = {t["transaction_id"] for t in bucket["transactions"]}
        assert ids == {"txn-a", "txn-b"}


class TestHiddenTransactions:
    """Transactions in a system-recognized transfer/payment category
    (IGNORE_CATEGORIES minus IGNORED_CATEGORY) — excluded from every total
    like IGNORED_CATEGORY, but surfaced (unlike before) for observation
    (2026-08-02, user-requested: "I still need to be able to see hidden
    transactions")."""

    def test_hidden_excluded_from_totals(self):
        df = make_df([
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "Payment - Thank You", 500.0, "CREDIT_CARD_PAYMENT"),
        ])
        totals, _, needs_review = _resolve_month(df, "2026-06")
        assert sum(totals.values()) == 5000.0
        assert needs_review == {}

    def test_hidden_bucketed_by_category(self):
        df = make_df([
            txn("2026-06-01", "Payment - Thank You", 500.0, "CREDIT_CARD_PAYMENT", transaction_id="txn-1"),
            txn("2026-06-02", "Online Banking transfer to SAV", 100.0, "BANK_TRANSFER", transaction_id="txn-2"),
        ])
        result = aggregate_month_json(df, "2026-06")
        categories = {b["category"] for b in result["hidden"]}
        assert categories == {"CREDIT_CARD_PAYMENT", "BANK_TRANSFER"}
        cc_bucket = next(b for b in result["hidden"] if b["category"] == "CREDIT_CARD_PAYMENT")
        assert cc_bucket["amount"] == 500.0
        assert cc_bucket["count"] == 1

    def test_user_ignored_category_excluded_from_hidden(self):
        """IGNORED_CATEGORY (the separate, user-driven "Ignore this
        transaction" feature) is technically a member of IGNORE_CATEGORIES
        too, but must not double-appear here -- it already has its own
        dedicated "ignored" list."""
        df = make_df([
            txn("2026-06-01", "Duplicate charge", 42.0, "IGNORED", transaction_id="txn-1"),
        ])
        result = aggregate_month_json(df, "2026-06")
        assert result["hidden"] == []
        assert len(result["ignored"]) == 1

    def test_no_hidden_transactions_returns_empty_list(self):
        df = make_df([txn("2026-06-01", "Employer Inc", 5000.0, "WAGES")])
        result = aggregate_month_json(df, "2026-06")
        assert result["hidden"] == []


class TestIgnoredTransactions:
    """The dashboard's "Ignore this transaction" action (RecategorizeModal.tsx)
    assigns IGNORED_CATEGORY via a transaction override — must be excluded
    from every total/the Sankey diagram like any other IGNORE_CATEGORIES
    entry, but still surfaced (with its note) for the dedicated Ignored
    section, purely for observation (2026-08-02, user-specified)."""

    def test_ignored_excluded_from_totals(self):
        df = make_df([
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "Duplicate charge", 42.0, "IGNORED", transaction_id="tx-ignore-1"),
        ])
        totals, _, needs_review = _resolve_month(df, "2026-06")
        assert sum(totals.values()) == 5000.0
        assert needs_review == {}

    def test_ignored_transaction_surfaced_with_note(self):
        overrides.add_transaction_override("tx-ignore-1", "IGNORED", "Reimbursed by roommate")
        df = make_df([
            txn("2026-06-02", "Duplicate charge", 42.0, "IGNORED", transaction_id="tx-ignore-1"),
        ])
        ignored = _ignored_transactions_for_month(df, "2026-06")
        assert len(ignored) == 1
        assert ignored[0]["transaction_id"] == "tx-ignore-1"
        assert ignored[0]["note"] == "Reimbursed by roommate"
        assert ignored[0]["amount"] == 42.0

    def test_ignored_transaction_without_note_is_none(self):
        df = make_df([
            txn("2026-06-02", "Duplicate charge", 42.0, "IGNORED", transaction_id="tx-no-note"),
        ])
        ignored = _ignored_transactions_for_month(df, "2026-06")
        assert ignored[0]["note"] is None

    def test_aggregate_month_json_includes_ignored_list(self):
        overrides.add_transaction_override("tx-ignore-1", "IGNORED", "test note")
        df = make_df([
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "Duplicate charge", 42.0, "IGNORED", transaction_id="tx-ignore-1"),
        ])
        result = aggregate_month_json(df, "2026-06")
        assert len(result["ignored"]) == 1
        assert result["ignored"][0]["note"] == "test note"
        income_section = next(s for s in result["sections"] if s["key"] == "income")
        zus = next(li for li in income_section["line_items"] if li["label"] == "Take Home Salary (Zus)")
        assert zus["actual"] == 5000.0

    def test_aggregate_range_json_concatenates_ignored_across_months(self):
        overrides.add_transaction_override("tx-1", "IGNORED", "note 1")
        overrides.add_transaction_override("tx-2", "IGNORED", "note 2")
        df = make_df([
            txn("2026-05-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-05-02", "Old duplicate", 10.0, "IGNORED", transaction_id="tx-1"),
            txn("2026-06-01", "Employer Inc", 5000.0, "WAGES"),
            txn("2026-06-02", "New duplicate", 20.0, "IGNORED", transaction_id="tx-2"),
        ])
        result = aggregate_range_json(df, ["2026-05", "2026-06"])
        assert len(result["ignored"]) == 2
        assert {t["note"] for t in result["ignored"]} == {"note 1", "note 2"}
