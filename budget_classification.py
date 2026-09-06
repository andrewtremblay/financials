"""
budget_classification.py — best-guess Need/Want tagging (plus Housing/Debt
sub-tags for the 28/36 rule) for every static line item in
budget_schema.BUDGET_SECTIONS, consumed by budget_rules.py.

This is genuinely subjective per household (is "Clothing" a need or a want?
depends who you ask) — these are defaults, not ground truth.
custom_budget_classification.py is the durable override layer; every real
caller should go through classify_line_item()/all_classifications() below,
never this module's dict directly, so overrides are never silently skipped.

Only expense-section line items are classified. Income line items aren't
part of any need/want/debt split, and every Savings-section line item counts
as "savings" by definition (see budget_rules.py) — neither needs an entry
here.
"""

import custom_budget_classification

# (section, label) -> {budget_type: "need"|"want", housing: bool, debt: bool}
# `housing`: counts toward the 28/36 rule's housing-cost side.
# `debt`: counts toward the 28/36 rule's total-debt-payments side (a line
# item can be both, e.g. a mortgage payment is Need + Housing + Debt).
#
# Caveat carried into the UI, not silently hidden: this app only sees Plaid
# transactions, never loan-servicing detail, so "debt" here can only ever
# capture the mortgage lines — an auto loan or student loan payment that
# isn't its own tracked line item (TRANSPORTATION currently has no such
# line) won't be counted, understating the 28/36 rule's debt side for
# anyone carrying non-mortgage debt (2026-08-02, flagged during design).
LINE_ITEM_BUDGET_TYPE: dict[tuple[str, str], dict] = {
    # HOME
    ("HOME", "Mortgage (12 Warren)"): {"budget_type": "need", "housing": True, "debt": True},
    ("HOME", "Mortgage + HOA (1 Cityview)"): {"budget_type": "need", "housing": True, "debt": True},
    ("HOME", "Home / Rental Insurance"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Electricity (Nat'l grid)"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Gas (Nat'l grid)"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Water / Sewer"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Phone (AT&T)"): {"budget_type": "need", "housing": False, "debt": False},
    ("HOME", "Internet (Xfinity)"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Furnishing / Appliances"): {"budget_type": "want", "housing": False, "debt": False},
    ("HOME", "Lawn / Garden"): {"budget_type": "want", "housing": False, "debt": False},
    ("HOME", "Maintenance / Improvements"): {"budget_type": "need", "housing": True, "debt": False},
    ("HOME", "Other"): {"budget_type": "want", "housing": False, "debt": False},

    # TRANSPORTATION
    ("TRANSPORTATION", "Registration / License"): {"budget_type": "need", "housing": False, "debt": False},
    ("TRANSPORTATION", "Auto Insurance"): {"budget_type": "need", "housing": False, "debt": False},
    ("TRANSPORTATION", "Fuel"): {"budget_type": "need", "housing": False, "debt": False},
    ("TRANSPORTATION", "Public Transportation"): {"budget_type": "need", "housing": False, "debt": False},
    ("TRANSPORTATION", "Repairs / Maintenance"): {"budget_type": "need", "housing": False, "debt": False},
    ("TRANSPORTATION", "Motor Vehicle Excise Tax"): {"budget_type": "need", "housing": False, "debt": False},

    # DAILY LIVING
    ("DAILY LIVING", "Groceries"): {"budget_type": "need", "housing": False, "debt": False},
    ("DAILY LIVING", "Dining Out"): {"budget_type": "want", "housing": False, "debt": False},
    ("DAILY LIVING", "Clothing"): {"budget_type": "want", "housing": False, "debt": False},
    ("DAILY LIVING", "Cleaning Service"): {"budget_type": "want", "housing": False, "debt": False},
    ("DAILY LIVING", "Hair & Nail Salon / Barber"): {"budget_type": "want", "housing": False, "debt": False},
    ("DAILY LIVING", "Gifts"): {"budget_type": "want", "housing": False, "debt": False},
    ("DAILY LIVING", "Other"): {"budget_type": "want", "housing": False, "debt": False},

    # ENTERTAINMENT (all wants)
    ("ENTERTAINMENT", "Streaming / Movies"): {"budget_type": "want", "housing": False, "debt": False},
    ("ENTERTAINMENT", "Concerts / Plays"): {"budget_type": "want", "housing": False, "debt": False},
    ("ENTERTAINMENT", "Sports"): {"budget_type": "want", "housing": False, "debt": False},
    ("ENTERTAINMENT", "Other"): {"budget_type": "want", "housing": False, "debt": False},

    # HEALTH
    ("HEALTH", "Health Insurance"): {"budget_type": "need", "housing": False, "debt": False},
    ("HEALTH", "Gym Membership"): {"budget_type": "want", "housing": False, "debt": False},
    ("HEALTH", "Doctors / Dentist Visits"): {"budget_type": "need", "housing": False, "debt": False},
    ("HEALTH", "Medicine / Prescriptions"): {"budget_type": "need", "housing": False, "debt": False},
    ("HEALTH", "Car Insurance"): {"budget_type": "need", "housing": False, "debt": False},
    ("HEALTH", "Umbrella Insurance"): {"budget_type": "need", "housing": False, "debt": False},

    # VACATION / HOLIDAY (all wants)
    ("VACATION / HOLIDAY", "Airfare"): {"budget_type": "want", "housing": False, "debt": False},
    ("VACATION / HOLIDAY", "Accommodations"): {"budget_type": "want", "housing": False, "debt": False},
    ("VACATION / HOLIDAY", "Food"): {"budget_type": "want", "housing": False, "debt": False},
    ("VACATION / HOLIDAY", "Souvenirs"): {"budget_type": "want", "housing": False, "debt": False},
    ("VACATION / HOLIDAY", "Rental Car / Ubers"): {"budget_type": "want", "housing": False, "debt": False},
    ("VACATION / HOLIDAY", "Other"): {"budget_type": "want", "housing": False, "debt": False},
}

# Applied to any expense line item with neither a static default above nor a
# user override — custom categories (see custom_categories.py) and synthetic
# stray-key entries (see budget_aggregate.aggregate_month_json) always fall
# here until the user tags them. Defaults to "want": a false "need" silently
# protects spending from the rules meant to flag it, so the safer unknown
# default is the one that shows up as discretionary.
FALLBACK_BUDGET_TYPE = {"budget_type": "want", "housing": False, "debt": False}


def classify_line_item(section: str, label: str) -> dict:
    """{budget_type, housing, debt} for one (section, label) — user override
    (custom_budget_classification.py) wins over the static default above,
    which wins over FALLBACK_BUDGET_TYPE."""
    overrides = custom_budget_classification.list_overrides()
    if (section, label) in overrides:
        return overrides[(section, label)]
    if (section, label) in LINE_ITEM_BUDGET_TYPE:
        return LINE_ITEM_BUDGET_TYPE[(section, label)]
    return FALLBACK_BUDGET_TYPE


def all_classifications(known_keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """classify_line_item for every key in known_keys, in one overrides load
    — used by the /api/budget-classification listing endpoint so the UI can
    show every line item's current tag without one overrides read per row."""
    overrides = custom_budget_classification.list_overrides()
    return {
        key: overrides.get(key) or LINE_ITEM_BUDGET_TYPE.get(key) or FALLBACK_BUDGET_TYPE
        for key in known_keys
    }
