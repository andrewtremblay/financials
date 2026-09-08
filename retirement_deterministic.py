"""
retirement_deterministic.py — the non-probabilistic models: category 1
(Straight-Line Compounding, Variable Return, Capital Utilization, Capital
Preservation), category 3 (4% Rule, Rule of 25, Constant Percentage), and
category 7 (LeanFIRE/FatFIRE/CoastFIRE/BaristaFIRE math) from the
Retirement Planning tab spec (2026-08-02, user-specified).

Every function takes `settings` (retirement_settings.get_settings()'s
shape) and returns a plain result dict — retirement_engine.py wraps each
in {key, label, description, result} for the API/frontend.
"""

from retirement_data import SIMULATION_YEARS, SP500_ANNUAL_RETURNS
from retirement_shared import (
    amortized_withdrawal,
    balance_at_retirement as _balance_at_retirement,
    real_rate_pct,
    years_in_retirement as _years_in_retirement,
    years_to_retirement as _years_to_retirement,
)

# ---------------------------------------------------------------- Category 1


def straight_line_compounding(s: dict) -> dict:
    """Static, unchanging return AND inflation for both the accumulation
    and decumulation phases — the simplest possible projection, and the
    baseline every other model implicitly compares against."""
    years_to_retirement = _years_to_retirement(s)
    years_in_retirement = _years_in_retirement(s)
    balance = _balance_at_retirement(s)
    real_return = real_rate_pct(s["annual_return_pct"], s["inflation_pct"])
    sustainable_withdrawal = amortized_withdrawal(balance, real_return, years_in_retirement)
    return {
        "years_to_retirement": round(years_to_retirement, 1),
        "years_in_retirement": round(years_in_retirement, 1),
        "balance_at_retirement": round(balance, 2),
        "real_return_pct": round(real_return, 2),
        "sustainable_annual_withdrawal_today_dollars": round(sustainable_withdrawal, 2),
        "meets_desired_spending": sustainable_withdrawal >= s["desired_annual_spending"],
    }


def variable_return_single_sequence(s: dict) -> dict:
    """Walks ONE specific, non-randomized sequence of changing annual
    returns (the bundled historical S&P 500 series, cycled if the horizon
    outlasts the data) through accumulation + a fixed 4%-Rule-style
    withdrawal in retirement — "variable" because the return changes every
    year, but there's only one deterministic pass, unlike Monte Carlo/
    Bootstrapping's many randomized trials."""
    years_to_retirement = int(round(_years_to_retirement(s)))
    years_in_retirement = int(round(_years_in_retirement(s)))
    n = len(SIMULATION_YEARS)

    balance = s["current_portfolio_balance"]
    for i in range(years_to_retirement):
        yr = SIMULATION_YEARS[i % n]
        balance = (balance + s["annual_savings"]) * (1 + SP500_ANNUAL_RETURNS[yr] / 100)
    balance_at_ret = balance

    withdrawal = balance_at_ret * s["withdrawal_rate_pct"] / 100
    depleted_in_year: int | None = None
    for j in range(years_in_retirement):
        yr = SIMULATION_YEARS[(years_to_retirement + j) % n]
        balance = (balance - withdrawal) * (1 + SP500_ANNUAL_RETURNS[yr] / 100)
        withdrawal *= 1 + s["inflation_pct"] / 100
        if balance <= 0 and depleted_in_year is None:
            depleted_in_year = j + 1
            break

    return {
        "balance_at_retirement": round(balance_at_ret, 2),
        "ending_balance": round(max(0.0, balance), 2),
        "depleted_after_years_in_retirement": depleted_in_year,
        "lasted_full_retirement": depleted_in_year is None,
    }


def capital_utilization(s: dict) -> dict:
    """Solves for the constant annual withdrawal that exhausts the
    portfolio to exactly zero at life_expectancy_age — spend it all,
    deliberately, rather than preserve anything for an estate."""
    balance = _balance_at_retirement(s)
    real_return = real_rate_pct(s["annual_return_pct"], s["inflation_pct"])
    withdrawal = amortized_withdrawal(balance, real_return, _years_in_retirement(s))
    return {
        "balance_at_retirement": round(balance, 2),
        "annual_withdrawal_today_dollars": round(withdrawal, 2),
        "target_ending_balance": 0.0,
    }


def capital_preservation(s: dict) -> dict:
    """Spend only the yield the portfolio generates, leaving the nominal
    principal untouched forever — no target end age, since the principal
    is never drawn down. Caveat: this protects nominal principal, not its
    purchasing power — inflation still erodes real spending power over
    time even though the dollar balance never shrinks."""
    balance = _balance_at_retirement(s)
    annual_yield = balance * s["annual_return_pct"] / 100
    return {
        "balance_at_retirement": round(balance, 2),
        "annual_yield_spendable": round(annual_yield, 2),
        "principal_preserved": round(balance, 2),
    }


# ---------------------------------------------------------------- Category 3


def four_percent_rule(s: dict) -> dict:
    """Withdraws withdrawal_rate_pct (conventionally 4%) of the portfolio
    in year one, then adjusts every subsequent year strictly for
    inflation — the classic Bengen/Trinity-Study rule."""
    balance = _balance_at_retirement(s)
    year_one_withdrawal = balance * s["withdrawal_rate_pct"] / 100
    years = _years_in_retirement(s)
    final_year_withdrawal = year_one_withdrawal * (1 + s["inflation_pct"] / 100) ** max(0, years - 1)
    return {
        "balance_at_retirement": round(balance, 2),
        "year_one_withdrawal": round(year_one_withdrawal, 2),
        "final_year_withdrawal_nominal": round(final_year_withdrawal, 2),
        "meets_desired_spending": year_one_withdrawal >= s["desired_annual_spending"],
    }


def rule_of_25(s: dict) -> dict:
    """Total savings target = desired annual spending x 25 (the algebraic
    inverse of a 4% withdrawal rate — generalizes to whatever
    withdrawal_rate_pct is actually set to)."""
    multiple = 100 / s["withdrawal_rate_pct"] if s["withdrawal_rate_pct"] else float("inf")
    target = s["desired_annual_spending"] * multiple
    balance = _balance_at_retirement(s)
    return {
        "multiple": round(multiple, 2),
        "target_portfolio": round(target, 2),
        "projected_balance_at_retirement": round(balance, 2),
        "on_track": balance >= target,
        "shortfall": round(max(0.0, target - balance), 2),
    }


def constant_percentage(s: dict) -> dict:
    """Withdraws a fixed PERCENTAGE of the remaining balance every year
    (not a fixed dollar amount) — the withdrawal naturally rises and falls
    with the portfolio, and can never literally hit zero, but a bad
    sequence still shrinks real spending power a lot. Illustrated here by
    walking the constant assumed return forward year by year (not a
    one-line formula, since the base shrinks/grows every year)."""
    balance = _balance_at_retirement(s)
    r = s["annual_return_pct"] / 100
    pct = s["withdrawal_rate_pct"] / 100
    withdrawals: list[float] = []
    for _ in range(int(round(_years_in_retirement(s)))):
        w = balance * pct
        withdrawals.append(w)
        balance = (balance - w) * (1 + r)
    return {
        "year_one_withdrawal": round(withdrawals[0], 2) if withdrawals else 0.0,
        "final_year_withdrawal": round(withdrawals[-1], 2) if withdrawals else 0.0,
        "ending_balance": round(balance, 2),
    }


# ---------------------------------------------------------------- Category 7


def _fire_number(annual_spending: float, withdrawal_rate_pct: float) -> float:
    return annual_spending * (100 / withdrawal_rate_pct) if withdrawal_rate_pct else float("inf")


def lean_fire(s: dict) -> dict:
    target = _fire_number(s["lean_annual_spending"], s["withdrawal_rate_pct"])
    balance = _balance_at_retirement(s)
    return {
        "target_portfolio": round(target, 2),
        "projected_balance_at_retirement": round(balance, 2),
        "already_there": s["current_portfolio_balance"] >= target,
    }


def fat_fire(s: dict) -> dict:
    target = _fire_number(s["fat_annual_spending"], s["withdrawal_rate_pct"])
    balance = _balance_at_retirement(s)
    return {
        "target_portfolio": round(target, 2),
        "projected_balance_at_retirement": round(balance, 2),
        "already_there": s["current_portfolio_balance"] >= target,
    }


def coast_fire(s: dict) -> dict:
    """The net worth needed TODAY so that, with zero further
    contributions, pure compounding alone reaches the traditional
    retirement number by retirement_age."""
    traditional_target = _fire_number(s["desired_annual_spending"], s["withdrawal_rate_pct"])
    years = _years_to_retirement(s)
    r = s["annual_return_pct"] / 100
    coast_number = traditional_target / ((1 + r) ** years) if years > 0 else traditional_target
    return {
        "traditional_retirement_target": round(traditional_target, 2),
        "coast_fire_number": round(coast_number, 2),
        "current_balance": round(s["current_portfolio_balance"], 2),
        "already_coast_fire": s["current_portfolio_balance"] >= coast_number,
        "shortfall": round(max(0.0, coast_number - s["current_portfolio_balance"]), 2),
    }


def barista_fire(s: dict) -> dict:
    """The portfolio needed to bridge just the GAP a part-time/lower-stress
    job doesn't cover — a smaller number than full FIRE, since
    barista_annual_spending_gap (not total spending) is the target base."""
    target = _fire_number(s["barista_annual_spending_gap"], s["withdrawal_rate_pct"])
    return {
        "target_portfolio": round(target, 2),
        "current_balance": round(s["current_portfolio_balance"], 2),
        "already_there": s["current_portfolio_balance"] >= target,
        "shortfall": round(max(0.0, target - s["current_portfolio_balance"]), 2),
    }
