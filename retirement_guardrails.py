"""
retirement_guardrails.py — category 4: Guyton-Klinger Rules, Variable
Percentage Withdrawal (VPW), Bengen's Floor-and-Ceiling Method, Ratchet
Rule, and Optimal Control Theory (2026-08-02, user-specified).

All five walk the portfolio forward year-by-year against the settings'
constant assumed nominal return — deterministic, like retirement_deterministic.py,
but each applies a different RULE for how the withdrawal amount itself
adapts to the portfolio's own trajectory (unlike the fixed/inflation-only
adjustments in the Static Withdrawal Rate Frameworks).
"""

import math

from retirement_shared import (
    amortized_withdrawal,
    balance_at_retirement,
    real_rate_pct,
    years_in_retirement,
)


def guyton_klinger(s: dict) -> dict:
    """"Capital Preservation" guardrail cuts spending 10% when the current
    withdrawal rate drifts 20% above the initial rate (the portfolio
    underperformed relative to spending); the "Prosperity" guardrail raises
    spending 10% when it drifts 20% below (the portfolio outperformed).
    Otherwise, spending just adjusts for inflation as usual."""
    balance = balance_at_retirement(s)
    initial_rate = s["withdrawal_rate_pct"] / 100
    withdrawal = balance * initial_rate
    r = s["annual_return_pct"] / 100
    infl = s["inflation_pct"] / 100
    years = max(1, int(round(years_in_retirement(s))))

    cuts = raises = 0
    depleted_after: int | None = None
    for year in range(years):
        current_rate = withdrawal / balance if balance > 0 else 0.0
        if current_rate > initial_rate * 1.20:
            withdrawal *= 0.90
            cuts += 1
        elif current_rate < initial_rate * 0.80:
            withdrawal *= 1.10
            raises += 1
        else:
            withdrawal *= 1 + infl
        balance = (balance - withdrawal) * (1 + r)
        if balance <= 0:
            depleted_after = year + 1
            break

    return {
        "balance_at_retirement": round(balance_at_retirement(s), 2),
        "year_one_withdrawal": round(balance_at_retirement(s) * initial_rate, 2),
        "guardrail_cuts_triggered": cuts,
        "guardrail_raises_triggered": raises,
        "ending_balance": round(max(0.0, balance), 2),
        "depleted_after_years": depleted_after,
    }


def variable_percentage_withdrawal(s: dict) -> dict:
    """Each year's withdrawal is the full amortized_withdrawal PMT against
    whatever balance and REMAINING years are left at that point — as
    remaining years shrink, the same real return implies a mechanically
    higher withdrawal rate, so VPW's rate rises with age by construction."""
    balance = balance_at_retirement(s)
    r = s["annual_return_pct"] / 100
    real_r = real_rate_pct(s["annual_return_pct"], s["inflation_pct"])
    years_total = max(1, int(round(years_in_retirement(s))))

    rates: list[float] = []
    withdrawals: list[float] = []
    for year in range(years_total):
        remaining = years_total - year
        # amortized_withdrawal assumes an ordinary annuity (payment at each
        # period's END); this loop withdraws THEN grows the remainder
        # (payment at the START), so at remaining=1 the raw formula
        # overshoots balance by a factor of (1+r) — clamp to what's
        # actually there, which correctly means "spend it all" in the
        # final year rather than a >100%-of-balance withdrawal driving the
        # ending balance negative.
        w = min(amortized_withdrawal(balance, real_r, remaining), balance)
        rates.append((w / balance * 100) if balance > 0 else 0.0)
        withdrawals.append(w)
        balance = (balance - w) * (1 + r)

    return {
        "year_one_withdrawal": round(withdrawals[0], 2) if withdrawals else 0.0,
        "year_one_withdrawal_rate_pct": round(rates[0], 2) if rates else 0.0,
        "final_year_withdrawal_rate_pct": round(rates[-1], 2) if rates else 0.0,
        "ending_balance": round(balance, 2),
    }


def bengen_floor_ceiling(s: dict, band_pct: float = 15.0) -> dict:
    """A Constant-Percentage-style "natural" withdrawal (balance x
    withdrawal_rate_pct, so it floats with the market) is clamped every
    year to stay within +/-band_pct of the original inflation-adjusted 4%-
    Rule trajectory — bounding both the worst-case spending cut and the
    best-case spending increase."""
    balance = balance_at_retirement(s)
    base_withdrawal = balance * s["withdrawal_rate_pct"] / 100
    floor = base_withdrawal * (1 - band_pct / 100)
    ceiling = base_withdrawal * (1 + band_pct / 100)
    r = s["annual_return_pct"] / 100
    infl = s["inflation_pct"] / 100
    years = max(1, int(round(years_in_retirement(s))))

    clamped_low = clamped_high = 0
    withdrawal = 0.0
    for _ in range(years):
        natural = balance * s["withdrawal_rate_pct"] / 100
        if natural < floor:
            withdrawal = floor
            clamped_low += 1
        elif natural > ceiling:
            withdrawal = ceiling
            clamped_high += 1
        else:
            withdrawal = natural
        # The floor/ceiling band is fixed in dollar terms (inflation-
        # adjusted only), independent of the actual remaining balance —
        # unlike Constant Percentage, this CAN outspend a badly-underfunded
        # plan; never let a single year's withdrawal exceed what's left.
        withdrawal = min(withdrawal, max(0.0, balance))
        balance = (balance - withdrawal) * (1 + r)
        floor *= 1 + infl
        ceiling *= 1 + infl

    return {
        "balance_at_retirement": round(balance_at_retirement(s), 2),
        "year_one_withdrawal": round(base_withdrawal, 2),
        "floor_year_one": round(base_withdrawal * (1 - band_pct / 100), 2),
        "ceiling_year_one": round(base_withdrawal * (1 + band_pct / 100), 2),
        "years_clamped_to_floor": clamped_low,
        "years_clamped_to_ceiling": clamped_high,
        "ending_balance": round(balance, 2),
    }


def ratchet_rule(s: dict, ratchet_threshold_pct: float = 20.0) -> dict:
    """Spending only ever adjusts for inflation OR ratchets UP when the
    portfolio has grown enough that resuming the initial withdrawal rate
    would mean a raise of ratchet_threshold_pct or more — once raised, the
    new higher floor is locked in and never cut, even in a later down
    market."""
    balance = balance_at_retirement(s)
    initial_rate = s["withdrawal_rate_pct"] / 100
    withdrawal = balance * initial_rate
    r = s["annual_return_pct"] / 100
    infl = s["inflation_pct"] / 100
    years = max(1, int(round(years_in_retirement(s))))

    ratchets = 0
    for _ in range(years):
        withdrawal *= 1 + infl
        sustainable_at_initial_rate = balance * initial_rate
        if sustainable_at_initial_rate > withdrawal * (1 + ratchet_threshold_pct / 100):
            withdrawal = sustainable_at_initial_rate
            ratchets += 1
        # The ratcheted floor never decreases even if the portfolio later
        # underperforms — that's the whole point of the rule — so a long
        # enough bad stretch can still outspend what's left; never let a
        # single year's withdrawal exceed the actual remaining balance.
        withdrawal = min(withdrawal, max(0.0, balance))
        balance = (balance - withdrawal) * (1 + r)

    return {
        "year_one_withdrawal": round(balance_at_retirement(s) * initial_rate, 2),
        "final_year_withdrawal": round(withdrawal, 2),
        "ratchets_triggered": ratchets,
        "ending_balance": round(balance, 2),
    }


def optimal_control_bellman(s: dict, grid_size: int = 50, discount: float = 0.96) -> dict:
    """A SIMPLIFIED deterministic Bellman-equation solve (backward
    induction over a discretized wealth grid, constant assumed return, no
    randomness) — maximizes total discounted CRRA utility
    (settings.risk_aversion = gamma) of consumption across retirement. A
    full stochastic dynamic program (optimizing against a real return
    distribution rather than one constant assumed path) is a substantially
    larger undertaking — flagged here rather than silently pretending this
    is that (2026-08-02, noted during design)."""
    balance0 = balance_at_retirement(s)
    if balance0 <= 0:
        return {"year_one_withdrawal": 0.0, "note": "No balance at retirement to optimize over."}

    r = s["annual_return_pct"] / 100
    gamma = s.get("risk_aversion", 3.0)
    years = max(1, int(round(years_in_retirement(s))))
    max_wealth = balance0 * 2.0

    def utility(c: float) -> float:
        c = max(c, 1e-6)
        if abs(gamma - 1.0) < 1e-9:
            return math.log(c)
        return (c ** (1 - gamma)) / (1 - gamma)

    wealth_grid = [max_wealth * i / (grid_size - 1) for i in range(grid_size)]
    fractions = [k / 50 for k in range(1, 51)]

    def interpolate(values: list[float], w: float) -> float:
        if w <= wealth_grid[0]:
            return values[0]
        if w >= wealth_grid[-1]:
            return values[-1]
        idx = w / max_wealth * (grid_size - 1)
        lo = int(idx)
        hi = min(lo + 1, grid_size - 1)
        frac = idx - lo
        return values[lo] * (1 - frac) + values[hi] * frac

    # Terminal period: consume whatever's left.
    value_next = [utility(w) for w in wealth_grid]
    policy_year_one = 0.0

    for t in range(years - 1, -1, -1):
        value_curr = [0.0] * grid_size
        policy_curr = [0.0] * grid_size
        for i, w in enumerate(wealth_grid):
            best_value = float("-inf")
            best_c = 0.0
            for frac in fractions:
                c = w * frac
                remaining = (w - c) * (1 + r)
                value = utility(c) + discount * interpolate(value_next, remaining)
                if value > best_value:
                    best_value = value
                    best_c = c
            value_curr[i] = best_value
            policy_curr[i] = best_c
        value_next = value_curr
        if t == 0:
            policy_year_one = interpolate(policy_curr, balance0)

    return {
        "balance_at_retirement": round(balance0, 2),
        "optimal_year_one_withdrawal": round(policy_year_one, 2),
        "risk_aversion_gamma": gamma,
    }
