"""
retirement_structuring.py — category 6: Asset-Liability Matching (ALM),
Time-Segmented Bucketing, Bond Ladder Mathematics (2026-08-02,
user-specified).
"""

from retirement_shared import balance_at_retirement, years_in_retirement


def asset_liability_matching(s: dict) -> dict:
    """Matches guaranteed income streams (Social Security, pension) against
    the fixed, non-negotiable liability of desired annual spending — the
    GAP left over is what the portfolio actually has to fund with
    guaranteed-income instruments (a bond ladder, an annuity) rather than
    market-exposed withdrawals."""
    guaranteed_income = s["social_security_annual"] + s["pension_annual"]
    gap = max(0.0, s["desired_annual_spending"] - guaranteed_income)
    # The portfolio needed to fully match the gap with a bond-like
    # guaranteed yield (bond_yield_pct), spent down to zero by
    # life_expectancy_age — reuses the same amortized-PMT math as Capital
    # Utilization, just at a conservative bond yield instead of the full
    # equity-blended return assumption, since ALM is specifically about
    # NOT relying on market returns for this portion.
    years = years_in_retirement(s)
    # Present-value-of-annuity formula: the inverse of
    # retirement_shared.amortized_withdrawal (which solves for PMT given a
    # balance) — here solving for the balance needed to sustain a given PMT.
    r = s["bond_yield_pct"] / 100
    portfolio_needed_to_match_gap = gap * (1 - (1 + r) ** -years) / r if r != 0 and years > 0 else gap * years
    return {
        "guaranteed_income_annual": round(guaranteed_income, 2),
        "annual_liability_gap": round(gap, 2),
        "portfolio_needed_to_fully_match_gap": round(portfolio_needed_to_match_gap, 2),
        "fully_matched_today": s["current_portfolio_balance"] >= portfolio_needed_to_match_gap,
    }


def time_segmented_bucketing(s: dict) -> dict:
    """Splits the portfolio at retirement into three chronological tiers:
    Bucket 1 (cash, years 1-5 of spending), Bucket 2 (bonds, years 6-10),
    Bucket 3 (equities, everything left for years 11+) — each bucket only
    needs to outrun the market risk appropriate to how soon it'll be
    spent."""
    balance = balance_at_retirement(s)
    annual_spending = s["desired_annual_spending"]
    bucket_1_cash = min(balance, annual_spending * 5)
    remaining = balance - bucket_1_cash
    bucket_2_bonds = min(remaining, annual_spending * 5)
    remaining -= bucket_2_bonds
    bucket_3_equities = max(0.0, remaining)
    return {
        "balance_at_retirement": round(balance, 2),
        "bucket_1_cash_years_1_5": round(bucket_1_cash, 2),
        "bucket_2_bonds_years_6_10": round(bucket_2_bonds, 2),
        "bucket_3_equities_years_11_plus": round(bucket_3_equities, 2),
    }


def bond_ladder(s: dict, max_rungs: int = 10) -> dict:
    """A bond_allocation-funded pool split into sequential annual-maturity
    rungs, each providing one year's guaranteed cash flow from principal
    return, plus its own coupon income at bond_yield_pct in the meantime —
    structural maturity math, not a market-return projection."""
    balance = balance_at_retirement(s)
    bond_pool = balance * 0.40  # illustrative fixed-income share of the portfolio at retirement
    years = max(1, int(round(s["life_expectancy_age"] - s["retirement_age"])))
    rungs = min(max_rungs, years)
    rung_value = bond_pool / rungs if rungs > 0 else 0.0
    annual_coupon_income = bond_pool * s["bond_yield_pct"] / 100
    return {
        "bond_pool": round(bond_pool, 2),
        "number_of_rungs": rungs,
        "value_per_rung": round(rung_value, 2),
        "annual_coupon_income_while_laddering": round(annual_coupon_income, 2),
    }
