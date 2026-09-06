"""
retirement_shared.py — compounding/withdrawal math shared across every
retirement_*.py model module (deterministic, guardrails, actuarial,
structuring, simulation) — kept in one place so e.g. "how is a real rate
computed" or "how does accumulation compound" can't quietly drift between
models that all claim to use the same assumptions.
"""


def years_to_retirement(s: dict) -> float:
    return max(0.0, s["retirement_age"] - s["current_age"])


def years_in_retirement(s: dict) -> float:
    return max(0.0, s["life_expectancy_age"] - s["retirement_age"])


def real_rate_pct(nominal_pct: float, inflation_pct: float) -> float:
    """Fisher equation: the inflation-adjusted (real) rate implied by a
    nominal rate and an inflation rate — used everywhere a model needs
    purchasing-power-preserving math rather than nominal-dollar math."""
    return ((1 + nominal_pct / 100) / (1 + inflation_pct / 100) - 1) * 100


def future_value_with_contributions(pv: float, annual_contribution: float, rate_pct: float, years: float) -> float:
    """FV of a lump sum plus an ordinary annuity of equal annual
    contributions (made at each year's end) — standard compounding math
    shared by every accumulation-phase projection."""
    r = rate_pct / 100
    if years <= 0:
        return pv
    fv_lump = pv * (1 + r) ** years
    fv_contributions = annual_contribution * (((1 + r) ** years - 1) / r) if r != 0 else annual_contribution * years
    return fv_lump + fv_contributions


def amortized_withdrawal(balance: float, rate_pct: float, years: float) -> float:
    """The constant annual withdrawal (PMT) that exactly depletes `balance`
    to zero over `years` at `rate_pct` — the shared formula behind Capital
    Utilization, the Life Expectancy Method, and each year of VPW."""
    r = rate_pct / 100
    if years <= 0:
        return balance
    if r == 0:
        return balance / years
    return balance * r / (1 - (1 + r) ** -years)


def balance_at_retirement(s: dict) -> float:
    return future_value_with_contributions(
        s["current_portfolio_balance"], s["annual_savings"], s["annual_return_pct"], years_to_retirement(s),
    )
