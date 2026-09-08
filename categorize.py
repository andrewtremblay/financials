import re

import overrides
from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE, output_parser, extract_date_and_amount_from_transaction, load_local_category_hints
from langchain_core.prompts import PromptTemplate

# Boilerplate bank-transfer / credit-card-payment / payroll descriptions follow
# fixed formats across institutions (e.g. "Online Banking transfer to SAV 1796
# Confirmation# ..."). These are unambiguous from the description alone, so we
# classify them directly instead of spending an LLM call (and risking
# "INPUT NEEDED" from a model that's never confident about boilerplate).
BOILERPLATE_CATEGORY_PATTERNS = [
    (re.compile(r"online (banking|payment) (transfer )?(to|from) (sav|chk)", re.I), "BANK_TRANSFER"),
    (re.compile(r"(mobile|online) banking (payment|transfer) to crd", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"payment from chk", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"^payment - thank you", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"^payment received", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"^online/mobile payment conf", re.I), "CREDIT_CARD_PAYMENT"),
    # BoA's recurring autopay draft for the credit card itself — same payment
    # as the CONF#-suffixed one-off above, just the auto-scheduled variant.
    # Was falling through to the LLM as "OTHER" and getting counted as a real
    # expense, double-counting money already reflected in the card's own
    # purchase transactions (2026-08-02, user-specified).
    (re.compile(r"^online/mobile recurring", re.I), "CREDIT_CARD_PAYMENT"),
    # The recurring $100 "DES:DEBIT" is a self-transfer to savings, not payroll
    # (2026-07-28, user-confirmed) — must precede the general indn:piccininni
    # PAYROLL rule below, which otherwise matches on name alone regardless of
    # direction.
    (re.compile(r"des:debit.*piccininni", re.I), "BANK_TRANSFER"),
    (re.compile(r"indn:piccininni|des:dirdep.*piccininni", re.I), "PAYROLL"),
    # User-confirmed specific merchants/deposits (2026-07-28): "Deposit Mobile
    # Banking" is Banneker's paycheck; "Clckpay" is the 1 Cityview HOA fee
    # (ClickPay is a property-management payment platform); "QUIZZI.A" wires
    # are freelance client income; "Jesson Oslin" is accountant services.
    (re.compile(r"^deposit mobile banking$", re.I), "PAYROLL"),
    (re.compile(r"^clckpay$", re.I), "HOA"),
    (re.compile(r"quizziai mercuryach|from quizzi\.a", re.I), "INCOME"),
    (re.compile(r"^jesson oslin", re.I), "ACCOUNTING"),
    # Biweekly $250+$250 auto-transfers to brokerage straight out of each Zus
    # paycheck (2026-07-29 review) — matches the sheet's "Managed Brokerages"
    # line and the C4 projected-salary formula's "-250 -250" deduction, so
    # this must map distinctly from generic SAVINGS (see sheets_sync.py,
    # which nets this amount out of Take Home Salary (Zus)).
    (re.compile(r"funds transfer to brokerage", re.I), "MANAGED_BROKERAGES"),
    # Two distinct mortgages pay through two distinct lenders/accounts:
    # M&T (BoA checking) is the 1 Cityview mortgage; Crosscountry (Schwab
    # Andrew Checking) is the 12 Warren mortgage.
    (re.compile(r"m\s?&\s?t mortgage", re.I), "MORTGAGE CITYVIEW"),
    (re.compile(r"crosscountry", re.I), "MORTGAGE WARREN"),
    (re.compile(r"credit card bill payment|ba electronic payment", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"cash rewards statement credit", re.I), "IGNORE"),
    # UTILITIES as returned by the LLM lumps a gas station in with real utility
    # bills, and doesn't distinguish the water bill from National Grid
    # (electric+gas). Split what's unambiguous; leave National Grid /
    # unrecognized utilities as UTILITIES for manual review.
    (re.compile(r"sunoco", re.I), "GAS"),
    (re.compile(r"quincy water", re.I), "WATER_SEWER"),
    (re.compile(r"^at&t$", re.I), "PHONE"),
    # User-confirmed specific merchants (2026-07-28): Ogunquit/Maine trip
    # dining, and three unrecognized merchants from the Q2 2026 INPUT NEEDED
    # review.
    (re.compile(r"front porch restau|tuscan sea grill|the egg & i|harbor creamery|ogunquit museum", re.I), "FOOD RESTAURANTS"),
    (re.compile(r"exoticdetma", re.I), "AUTO_MAINTENANCE"),
    (re.compile(r"chitaliving", re.I), "FURNITURE"),
    (re.compile(r"sshore hospital", re.I), "MEDICAL"),
    # User-confirmed (2026-07-28), second pass on Q2 INPUT NEEDED review.
    (re.compile(r"^claude\.ai$", re.I), "SUBSCRIPTION"),
    (re.compile(r"pspt ogunqt prk", re.I), "TRANSPORTATION"),
    (re.compile(r"^monitordata$|^prestige services$", re.I), "OTHER"),

    # ── Full-history INPUT NEEDED sweep (2026-07-28) ──────────────────────────
    # User-confirmed: 690 Adams St deposits and the Citizens Bank/Check 416
    # items are housing-related; the Piccininni CASHREWARD ACH is a rewards
    # payout (same treatment as the existing "cash rewards statement credit").
    # 690 Adams St deposits are credit card payments, not apartment rental
    # income (2026-07-29, user-corrected) — excluded like any other
    # CREDIT_CARD_PAYMENT, not counted as income.
    (re.compile(r"bofa fin ctr.*690 adams st", re.I), "CREDIT_CARD_PAYMENT"),
    (re.compile(r"citizens bank 65 newpor quincy", re.I), "HOUSING"),
    (re.compile(r"^check 416$", re.I), "HOUSING"),
    # 2026-07-29 review: Check Paid #107 and the matching BKOFAMERICA MOBILE
    # deposit are the same $3017 moving between the user's own accounts via a
    # physical check — a self-transfer, not income or an expense.
    (re.compile(r"^check paid #107$", re.I), "BANK_TRANSFER"),
    (re.compile(r"bkofamerica mobile 07/18 xxxxx48465 deposit", re.I), "BANK_TRANSFER"),
    # 2026-07-29 review: every INSURANCE-categorized transaction in Apr-Jul
    # 2026 is "Plymouth Rock As[surance]" at the same recurring amount as the
    # sheet's existing Auto Insurance line — split out from generic INSURANCE
    # (which elsewhere includes e.g. Allianz, not necessarily auto) so it maps
    # unambiguously.
    (re.compile(r"plymouth rock as", re.I), "INSURANCE_AUTO"),
    (re.compile(r"des:cashreward.*piccininni", re.I), "IGNORE"),
    (re.compile(r"^alba$", re.I), "FOOD RESTAURANTS"),
    # Mobile parking-payment apps (Passport/other) format as "P######" or
    # "LK######" followed by a street address; municipal parking-meter charges
    # show as "City Of <town>" or "<town> Parking". Both are parking.
    (re.compile(r"^(p|lk)\d{6}\s", re.I), "TRANSPORTATION"),
    (re.compile(r"city of (quincy|newburyport|somerville)|brookline passport pkg|mbta ", re.I), "TRANSPORTATION"),
    # Benjamin Banneke DES:Receivable via Bill.com — same payer/relationship as
    # the existing "Deposit Mobile Banking" PAYROLL rule above.
    (re.compile(r"benjamin banneke.*receivable", re.I), "PAYROLL"),
    # Restaurants/bars/cafes identified by name from the Q2 review, applied
    # across full history.
    (re.compile(
        r"lsu the port of call|lsu oyster club|red 36|drifterskitchen|gufo|novara|genki ya|"
        r"mystic pizza|wei shu wu hot pot|off the hook bar|victory point|omori izakaya|"
        r"korean grille|dotty's kitchen|^la baia$|maria's trattoria|the mariner|larb b zaab|"
        r"inishmor|reelhouse oyster|the haven at the|zhi wei cafe|lighthouse bakery|"
        r"somewhere else tavern|family pizza resta|^patio$|^yoki$|engine room|asian cafe corp|"
        r"lucys american tav|omonia cafe|bishop hill tavern|laderach|fox farm brewery|"
        r"sugar & spice|danger bar|bellahera|dagu rice noodle|tiki rock|cafe mami|"
        r"joystick gamebar|jimmy s broad st cafe|shake shack|bank & bridge bre|"
        r"fresh bread & past|widowmaker brewing|new england free|table nine hospita|"
        r"hunters beach bar|thats italian too|jfk t5 fc lucys|the lunch box conc|elbow room|"
        r"high street place|ned devine's|mcdonald's|handle bar|kung fu tea",
        re.I,
    ), "FOOD RESTAURANTS"),
    (re.compile(r"sshs pb central busine|braintree dental group|genova diagnostics|dentpart", re.I), "MEDICAL"),
    (re.compile(r"natick prenata", re.I), "MEDICAL"),
    # CVS is pharmacy/prescriptions, not a doctor visit (2026-07-29,
    # user-specified) — split from Walgreens, still HEALTH.
    (re.compile(r"^cvs$", re.I), "MEDICINE"),
    (re.compile(r"^walgreens$", re.I), "HEALTH"),
    (re.compile(r"^shell$", re.I), "GAS"),
    (re.compile(r"^a\.l\. prime$", re.I), "GAS"),
    # Wollaston Wine & Spirits should be Groceries, not lumped in with other
    # liquor stores under LIQUOR (2026-07-29, user-specified).
    (re.compile(r"wollaston wine and spi", re.I), "GROCERIES"),
    (re.compile(r"colchester wine and sp", re.I), "LIQUOR"),
    (re.compile(r"the fruit center inc|belltown hill orch", re.I), "GROCERIES"),
    (re.compile(r"momcozy|free jacks shop|quality consignments|simplylitcand|paper source|ipersonalized", re.I), "RETAIL"),
    (re.compile(r"bank square books", re.I), "BOOKS"),
    (re.compile(r"^sephora$", re.I), "BEAUTY"),
    (re.compile(r"the outsiders tour|ica boston|harvard museum of natu|dcu center|mystic museum of a|the great america", re.I), "ENTERTAINMENT"),
    (re.compile(r"^allianz$", re.I), "INSURANCE"),
    (re.compile(r"^ppl$", re.I), "UTILITIES"),
    (re.compile(r"washington department of revenue|tax pmnt conven fee", re.I), "TAX"),
    (re.compile(r"gannett media co", re.I), "SUBSCRIPTION"),
    (re.compile(r"the home depot", re.I), "HARDWARE"),
    (re.compile(r"^7-eleven$", re.I), "RETAIL"),
    (re.compile(r"^ramp acctverify", re.I), "IGNORE"),
    (re.compile(r"^jetblue$|^cathay pacific airways$", re.I), "TRAVEL"),
    (re.compile(r"^primary annual fee$", re.I), "FEES"),
    # User-confirmed (2026-07-28), third pass on full-history INPUT NEEDED review.
    (re.compile(r"^venmo$", re.I), "FOOD RESTAURANTS"),
    (re.compile(r"spencer & lynn|^kelley$", re.I), "HAIR"),
    (re.compile(r"^soleil llc$|ls linen press sound", re.I), "GIFTS"),
    # User-confirmed (2026-07-28), fourth pass — guesses walked through with
    # the user one by one; several corrected my initial guess (noted).
    (re.compile(r"boston evening the", re.I), "ENTERTAINMENT"),
    (re.compile(r"^citizens bank opera hboston$", re.I), "ENTERTAINMENT"),
    (re.compile(r"^versus$", re.I), "ENTERTAINMENT"),  # not clothing — guessed wrong
    (re.compile(r"^quincy mv$", re.I), "TAX"),
    (re.compile(r"^assembly$", re.I), "FOOD RESTAURANTS"),  # not retail — guessed wrong
    (re.compile(r"^milestone$", re.I), "GAS"),  # not a restaurant chain — guessed wrong
    (re.compile(r"^parchment$", re.I), "GIFTS"),  # not education/transcripts — guessed wrong
    (re.compile(r"collinswood mushro", re.I), "GROCERIES"),
    (re.compile(r"ottrsupply", re.I), "HOME_IMPROVEMENT"),  # not pet/outdoor retail — guessed wrong
    (re.compile(r"thewishingwel", re.I), "RETAIL"),
    (re.compile(r"flyingpigprin", re.I), "RETAIL"),
    (re.compile(r"^hive$|^lore$", re.I), "FOOD RESTAURANTS"),
    # User-confirmed (2026-07-28), fifth and final pass — last of the
    # full-history INPUT NEEDED sweep.
    (re.compile(r"janelle imports|^halo dream$|^q street d$|^source$", re.I), "GIFTS"),
    (re.compile(r"^guntherto$", re.I), "FOOD RESTAURANTS"),
    (re.compile(r"^the roadrunners$", re.I), "GAS"),
    (re.compile(r"^star$", re.I), "GROCERIES"),
    # Baby registry / maternity wear were getting swept into SUBSCRIPTION ->
    # Streaming/Movies; belong in Gifts instead (2026-07-29, user-specified).
    (re.compile(r"^babylist$|^kindred bravely$", re.I), "GIFTS"),
    # Generic recurring-charge statement line, not a real subscription ->
    # Daily Living Other (2026-07-29, user-specified).
    (re.compile(r"online/mobile recurring", re.I), "OTHER"),
]


def classify_boilerplate(description: str, amount: float | None = None) -> str | None:
    """Return a category for known boilerplate bank descriptions, or None if the
    description needs the LLM (or a human) to categorize it."""
    # The $250 INSPERI PAYROLL deposit (alongside the much larger main
    # paycheck deposit, same description) is the emergency fund contribution
    # split off from Zus's paycheck, not take-home salary (2026-07-29,
    # user-confirmed) — matches the sheet's own C4 note ("250 separately
    # deposited to savings for the emergency fund"). Must precede the general
    # WAGES categorization below, which can't see the amount.
    if amount is not None and abs(amount - 250.00) < 0.01 and "insperi payroll" in description.lower():
        return "EMERGENCY_FUND_ZUS"
    for pattern, category in BOILERPLATE_CATEGORY_PATTERNS:
        if pattern.search(description):
            return category
    return None


# 2026-07-29: bare "FOOD" and "GROCERIES" are too vague ("Food Direct" in the
# sankey doesn't say whether it's takeout or groceries). A review of every
# bare-FOOD transaction in history showed it's ~100% dining out (Dunkin',
# pizza shops, cafes, bakeries) — none of it groceries, which the LLM/
# boilerplate already separates out correctly by merchant name. So fold both
# into the FOOD hierarchy: GROCERIES becomes a proper FOOD subcategory
# alongside RESTAURANTS, and bare FOOD (the LLM's fallback for dining
# merchants it doesn't have a specific rule for) becomes FOOD RESTAURANTS.
CATEGORY_NORMALIZATION = {
    "FOOD": "FOOD RESTAURANTS",
    "GROCERIES": "FOOD GROCERIES",
    "GROCERY": "FOOD GROCERIES",  # LLM singular/plural inconsistency, same merchants
}


def normalize_category(category: str) -> str:
    return CATEGORY_NORMALIZATION.get(category, category)


BA_CATEGORIES = "BA ELECTRONIC PAYMENT is a CREDIT CARD PAYMENT. "
BILL_CATEGORIES = "ATT is a PHONE BILL. "
INTEREST_CATEGORIES = "INTEREST CHARGED is a INTEREST category. "
SUBSCRIPTION_CATEGORIES = "1PASSWORD and APPLE.COM are each a SUBSCRIPTION category. "
# Personal merchant/payee hints come from a gitignored local file (see
# category_hints.example.txt), never from committed source.
LOCAL_CATEGORY_HINTS = load_local_category_hints()

categorize_prompt = PromptTemplate.from_template(CATEGORY_PROMPT
    + BA_CATEGORIES
    + BILL_CATEGORIES
    + SUBSCRIPTION_CATEGORIES
    + INTEREST_CATEGORIES
    + LOCAL_CATEGORY_HINTS
    + CATEGORY_UPPERCASE
    + UNCERTAINTY 
    + CATEGORY_SINGLE_WORD 
    + ONLY_PRINT_CATEGORY 
    + TRANSACTION_PARAM)


def categorize_with_prompt(model: any, prompt, transactions: list[list[str]], transaction_ids: list[str | None] | None = None) -> list[dict]:
    """
    Same as categorize(), but with an explicit prompt template — lets callers
    (e.g. plaid_sync.py) pick a bank-specific prompt (boa_prompt, schwab_prompt,
    etc.) instead of always using the generic categorize_prompt.

    `transaction_ids`, if given, must be the same length as `transactions`
    (parallel list, not a 4th tuple element — keeps the PDF pipeline's
    3-element [date, description, amount] contract untouched, since it has
    no stable transaction IDs at all). Used to check for a manual
    per-transaction category override before falling to classify_boilerplate
    or the LLM; a merchant-wide override rule is checked regardless of
    whether transaction_ids was passed, since it's description-based.
    """
    chain = prompt | model | output_parser
    categorized_data = []
    for i, transaction in enumerate(transactions):
        raw_transaction = f"{transaction}"
        if(len(transaction) != 3):
            raise Exception(f"Invalid transaction: {raw_transaction}")
        date = transaction[0]
        description = transaction[1]
        amount = transaction[2]
        transaction_id = transaction_ids[i] if transaction_ids else None
        category = (
            overrides.lookup_transaction_override(transaction_id)
            or overrides.lookup_merchant_rule(description, amount)
            or classify_boilerplate(description, amount)
            or memoized_invoke_chain_transaction(chain, description)
        )
        category = normalize_category(category)
        categorized_data.append({"raw_transaction": raw_transaction, "description": description, "date": date, "amount": amount, "category": category})

    return categorized_data


def categorize(model: any, transactions: list[list[str]]) -> list[dict]:
    return categorize_with_prompt(model, categorize_prompt, transactions)
