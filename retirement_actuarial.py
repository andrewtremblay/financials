"""
retirement_actuarial.py — category 5: Life Expectancy Method, IRS RMD Math,
Gompertz-Makeham Longevity Function (2026-08-02, user-specified).
"""

import math

from retirement_data import GOMPERTZ_MAKEHAM_A, GOMPERTZ_MAKEHAM_B, GOMPERTZ_MAKEHAM_C, rmd_divisor
from retirement_shared import balance_at_retirement as _balance_at_retirement


def life_expectancy_method(s: dict) -> dict:
    """Divides the current balance by remaining statistical years to
    life_expectancy_age — recomputed every year in practice (both the
    balance and the remaining-years denominator shrink), so this reports
    year one only, plus the trajectory's shape."""
    balance_at_retirement = _balance_at_retirement(s)
    remaining_years = max(1.0, s["life_expectancy_age"] - s["retirement_age"])
    year_one_withdrawal = balance_at_retirement / remaining_years
    return {
        "balance_at_retirement": round(balance_at_retirement, 2),
        "remaining_years_at_retirement": round(remaining_years, 1),
        "year_one_withdrawal": round(year_one_withdrawal, 2),
    }


def irs_rmd_schedule(s: dict) -> dict:
    """Required Minimum Distributions per the IRS Uniform Lifetime Table
    (retirement_data.py) from age 72 (or retirement_age if later) through
    life_expectancy_age — mandatory withdrawals regardless of whether the
    money is actually needed that year."""
    balance = _balance_at_retirement(s)
    r = s["annual_return_pct"] / 100
    start_age = max(72, int(round(s["retirement_age"])))
    end_age = int(round(s["life_expectancy_age"]))
    schedule = []
    age = start_age
    # Grow the balance untouched from retirement to the RMD start age.
    years_until_rmds = max(0, start_age - s["retirement_age"])
    balance *= (1 + r) ** years_until_rmds
    while age <= end_age and balance > 0:
        divisor = rmd_divisor(age)
        rmd = balance / divisor
        schedule.append({"age": age, "rmd": round(rmd, 2), "balance_before": round(balance, 2)})
        balance = (balance - rmd) * (1 + r)
        age += 1
    return {
        "start_age": start_age,
        "first_year_rmd": schedule[0]["rmd"] if schedule else 0.0,
        "schedule": schedule,
    }


def gompertz_makeham(s: dict) -> dict:
    """mu(x) = A + B*c^x (Makeham's law) gives the instantaneous mortality
    hazard at age x; integrating gives the survival function S(x). Reports
    the survival probability to life_expectancy_age and the age at which
    survival probability drops to 50% (the model's own implied median
    lifespan) — a way to sanity-check the settings' own
    life_expectancy_age assumption against a real actuarial function
    rather than a single hand-picked number."""
    a, b, c = GOMPERTZ_MAKEHAM_A, GOMPERTZ_MAKEHAM_B, GOMPERTZ_MAKEHAM_C
    x0 = s["current_age"]

    def survival(x: float) -> float:
        # S(x)/S(x0), i.e. probability of surviving from x0 to x.
        integral = a * (x - x0) + (b / math.log(c)) * (c**x - c**x0)
        return math.exp(-integral)

    survival_to_life_expectancy = survival(s["life_expectancy_age"])

    # Find the age where survival probability crosses 50% via simple
    # forward stepping (monotonically decreasing function, coarse
    # resolution is fine for a summary statistic).
    median_age = x0
    while survival(median_age) > 0.5 and median_age < x0 + 120:
        median_age += 0.25

    return {
        "current_age": x0,
        "survival_probability_to_life_expectancy": round(survival_to_life_expectancy, 4),
        "implied_median_lifespan": round(median_age, 1),
    }
