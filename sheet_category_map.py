"""
sheet_category_map.py — maps categorize.py's Plaid categories onto the
specific line items used by the household budget Google Sheet (one tab per
month, columns B=income/savings, H=expenses; see sheets_sync.py).

Built 2026-07-28 from categorize.py's observed category taxonomy across
data/plaid/*_categorized.csv. Categories not listed here (or explicitly in
NEEDS_REVIEW) are surfaced by sheets_sync.py as unmapped rather than guessed
into a line — several sheet line items (e.g. Auto Insurance vs Health
Insurance vs Umbrella Insurance) can't be told apart from the category alone.
"""

# The pseudo-category the dashboard's "Ignore this transaction" action
# assigns (api_server.py's TransactionCategoryUpdate, RecategorizeModal.tsx)
# — never produced by the LLM or a boilerplate pattern, only by explicit user
# action. Included in IGNORE_CATEGORIES below so it's excluded from every
# total/the Sankey diagram the same as a real transfer/payment, but tracked
# separately (with the user's note) for the dashboard's dedicated Ignored
# section — see budget_aggregate._ignored_transactions_for_month
# (2026-08-02, user-specified: observation-only, never double-counted).
IGNORED_CATEGORY = "IGNORED"

# categories that are transfers/payments between the user's own accounts —
# never income or expense, always excluded.
IGNORE_CATEGORIES = {"IGNORE", "BANK_TRANSFER", "CREDIT_CARD_PAYMENT", "VENMO_PAYMENT", IGNORED_CATEGORY}

# category -> (section, line item). "section" is "income" or "savings" for
# column B, or the expense group name (matching the sheet's H-column headers)
# for column H.
CATEGORY_TO_LINE_ITEM = {
    # INCOME
    "WAGES": ("income", "Take Home Salary (Zus)"),
    "PAYROLL": ("income", "Take Home Salary (Banneker)"),
    "INTEREST": ("income", "Interest Income"),
    "INCOME": ("income", "Misc."),
    # Apartment Rental Income has no confirmed Plaid source yet — the 690
    # Adams St deposits initially assumed to be this turned out to be credit
    # card payments instead (2026-07-29, user-corrected; now CREDIT_CARD_
    # PAYMENT in categorize.py, excluded like any other self-transfer).

    # SAVINGS — SAVINGS/INVESTMENT_METALS can't be told apart from Managed
    # Brokerages vs Home Projects vs Other Savings without per-transaction
    # detail, so both land in Other Savings pending manual review.
    # The $250 INSPERI PAYROLL split (2026-07-29) — same paycheck as WAGES,
    # but routed straight to the emergency fund rather than take-home pay.
    "EMERGENCY_FUND_ZUS": ("savings", "Emergency Fund"),
    "SAVINGS": ("savings", "Other Savings"),
    "INVESTMENT_METALS": ("savings", "Other Savings"),
    "MANAGED_BROKERAGES": ("savings", "Managed Brokerages"),

    # EXPENSES — HOME
    "MORTGAGE WARREN": ("HOME", "Mortgage (12 Warren)"),
    "MORTGAGE CITYVIEW": ("HOME", "Mortgage + HOA (1 Cityview)"),
    "HOA": ("HOME", "Mortgage + HOA (1 Cityview)"),
    "WATER_SEWER": ("HOME", "Water / Sewer"),
    "PHONE": ("HOME", "Phone (AT&T)"),
    "CABLE": ("HOME", "Internet (Xfinity)"),
    "HOME": ("HOME", "Furnishing / Appliances"),
    "FURNITURE": ("HOME", "Furnishing / Appliances"),
    # Home Depot (the only HARDWARE source) is home repair/improvement, not
    # furnishing (2026-07-29, user-specified).
    "HARDWARE": ("HOME", "Maintenance / Improvements"),
    "GARDEN": ("HOME", "Lawn / Garden"),
    "ACCOUNTING": ("HOME", "Other"),
    "OFFICE": ("HOME", "Other"),
    "SUPPLIES": ("HOME", "Other"),
    # No general "Taxes" line exists; household tax payments (e.g. IRS
    # estimated payments) land in HOME > Other as the closest catch-all
    # (2026-07-29 review).
    "TAX": ("HOME", "Other"),

    # EXPENSES — TRANSPORTATION (no "Other" line in this section, so
    # incidental categories fall back to Public Transportation)
    "GAS": ("TRANSPORTATION", "Fuel"),
    "TRANSPORTATION": ("TRANSPORTATION", "Public Transportation"),
    "PARKING": ("TRANSPORTATION", "Public Transportation"),
    "TOLL": ("TRANSPORTATION", "Public Transportation"),
    "AUTO": ("TRANSPORTATION", "Repairs / Maintenance"),
    "AUTO_MAINTENANCE": ("TRANSPORTATION", "Repairs / Maintenance"),
    "INSURANCE_AUTO": ("TRANSPORTATION", "Auto Insurance"),

    # EXPENSES — DAILY LIVING
    "GROCERY": ("DAILY LIVING", "Groceries"),
    "GROCERIES": ("DAILY LIVING", "Groceries"),
    "FOOD": ("DAILY LIVING", "Dining Out"),
    "RESTAURANT": ("DAILY LIVING", "Dining Out"),
    "CLOTHING": ("DAILY LIVING", "Clothing"),
    "SHOES": ("DAILY LIVING", "Clothing"),
    "SALON": ("DAILY LIVING", "Hair & Nail Salon / Barber"),
    "BEAUTY": ("DAILY LIVING", "Hair & Nail Salon / Barber"),
    "HAIR": ("DAILY LIVING", "Hair & Nail Salon / Barber"),
    "GIFTS": ("DAILY LIVING", "Gifts"),
    "RETAIL": ("DAILY LIVING", "Other"),
    "E-COMMERCE": ("DAILY LIVING", "Other"),
    "MISC": ("DAILY LIVING", "Other"),
    "ALCOHOL": ("DAILY LIVING", "Other"),
    "LIQUOR": ("DAILY LIVING", "Other"),
    "BOOKS": ("DAILY LIVING", "Other"),
    "ART": ("DAILY LIVING", "Other"),
    "OUTDOORS": ("DAILY LIVING", "Other"),
    # Credit-card annual fee and small unidentified vendors (2026-07-29
    # review) — too small/ambiguous to warrant their own line.
    "FEES": ("DAILY LIVING", "Other"),
    "OTHER": ("DAILY LIVING", "Other"),

    # EXPENSES — ENTERTAINMENT
    "SUBSCRIPTION": ("ENTERTAINMENT", "Streaming / Movies"),
    "ENTERTAINMENT": ("ENTERTAINMENT", "Other"),

    # EXPENSES — HEALTH
    "HEALTH": ("HEALTH", "Doctors / Dentist Visits"),
    "MEDICINE": ("HEALTH", "Medicine / Prescriptions"),
    "MEDICAL": ("HEALTH", "Doctors / Dentist Visits"),
    "DENTAL": ("HEALTH", "Doctors / Dentist Visits"),
    "RECREATION": ("HEALTH", "Gym Membership"),

    # EXPENSES — VACATION / HOLIDAY
    "TRAVEL": ("VACATION / HOLIDAY", "Airfare"),
    "HOTEL": ("VACATION / HOLIDAY", "Accommodations"),
}

# Categories seen in the data that are NOT auto-mapped to any line item —
# either because the dollar amount legitimately splits across multiple sheet
# lines (INSURANCE) or the transaction description alone doesn't say enough
# (CHECK, DEPOSIT, TAX, CREDIT, UTILITIES/UTILITY, INPUT NEEDED). Reported by
# sheets_sync.py per month/account so nothing is silently mis-allocated.
NEEDS_REVIEW_CATEGORIES = {
    # Generic INSURANCE (not the specific INSURANCE_AUTO carve-out above)
    # still legitimately splits across Home/Health/Umbrella and can't be told
    # apart from the category alone.
    "INSURANCE",
    "CHECK", "DEPOSIT", "CREDIT",
    "INPUT NEEDED",
    # HOUSING (Citizens Bank/Check 416 only, after the Adams St carve-out
    # above) mixes unrelated charges under one label with no debit/credit
    # sign, so income vs. expense can't be told apart here.
    "HOUSING",
    # UTILITIES is handled specially in sheets_sync.aggregate_month (National
    # Grid bills electric+gas together — split 50/50 rather than guessed
    # into one line; other utility vendors route to HOME > Other there).
    "UTILITIES", "UTILITY",
}
