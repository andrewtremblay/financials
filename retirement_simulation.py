"""
retirement_simulation.py — category 2: Monte Carlo Simulation,
Bootstrapping (Resampling), Historical Simulation (Backtesting), and
Regime-Switching Models (2026-08-02, user-specified).

All four start from balance_at_retirement(settings) and simulate
years_in_retirement(settings) years of a 4%-Rule-style withdrawal
(inflation-adjusted each year) under different return-generating
processes — the standard "success rate" framing this class of technique is
conventionally used for. Historical return data comes from
retirement_data.py's SP500_ANNUAL_RETURNS — see that module's docstring
for the data-quality disclaimer (illustrative, not an audited historical
record).
"""

import random
import statistics

from retirement_data import SIMULATION_YEARS, SP500_ANNUAL_RETURNS
from retirement_shared import balance_at_retirement, years_in_retirement

_MEAN_RETURN = statistics.mean(SP500_ANNUAL_RETURNS.values())
_STDEV_RETURN = statistics.stdev(SP500_ANNUAL_RETURNS.values())


def _simulate_withdrawal_sequence(starting_balance: float, withdrawal_rate_pct: float, inflation_pct: float, returns_pct: list[float]) -> bool:
    """Runs one ordered sequence of annual returns against a 4%-Rule-style
    withdrawal (inflation-adjusted every year after year one). Returns
    True if the balance never depletes before the sequence ends."""
    balance = starting_balance
    withdrawal = starting_balance * withdrawal_rate_pct / 100
    for ret in returns_pct:
        balance = (balance - withdrawal) * (1 + ret / 100)
        if balance <= 0:
            return False
        withdrawal *= 1 + inflation_pct / 100
    return True


def monte_carlo(s: dict, trials: int = 1000, seed: int | None = 42) -> dict:
    """Draws each trial's annual returns independently from a normal
    distribution matching the bundled historical series' own mean/stdev —
    a common simplification of the conventional "log-normal" Monte Carlo
    approach, using real historical mean/stdev rather than a hand-picked
    distribution."""
    rng = random.Random(seed)
    balance = balance_at_retirement(s)
    years = max(1, int(round(years_in_retirement(s))))
    successes = 0
    for _ in range(trials):
        returns = [rng.gauss(_MEAN_RETURN, _STDEV_RETURN) for _ in range(years)]
        if _simulate_withdrawal_sequence(balance, s["withdrawal_rate_pct"], s["inflation_pct"], returns):
            successes += 1
    return {
        "trials": trials,
        "years_simulated": years,
        "success_rate_pct": round(successes / trials * 100, 1),
        "assumed_mean_return_pct": round(_MEAN_RETURN, 2),
        "assumed_stdev_pct": round(_STDEV_RETURN, 2),
    }


def bootstrapping(s: dict, trials: int = 1000, seed: int | None = 42) -> dict:
    """Instead of a parametric normal draw, each trial's annual returns are
    drawn WITH REPLACEMENT from the actual bundled historical annual
    returns — preserves the real historical distribution's shape (fat
    tails, skew) instead of assuming normality."""
    rng = random.Random(seed)
    balance = balance_at_retirement(s)
    years = max(1, int(round(years_in_retirement(s))))
    pool = list(SP500_ANNUAL_RETURNS.values())
    successes = 0
    for _ in range(trials):
        returns = [rng.choice(pool) for _ in range(years)]
        if _simulate_withdrawal_sequence(balance, s["withdrawal_rate_pct"], s["inflation_pct"], returns):
            successes += 1
    return {
        "trials": trials,
        "years_simulated": years,
        "success_rate_pct": round(successes / trials * 100, 1),
    }


def historical_simulation(s: dict) -> dict:
    """Walks every possible CONTIGUOUS real historical window long enough
    to cover the full retirement horizon (no randomization, no
    replacement) — e.g. "if you'd retired in 1987," "if you'd retired in
    1988," etc. — and reports how many of those real windows would have
    survived."""
    balance = balance_at_retirement(s)
    years = max(1, int(round(years_in_retirement(s))))
    n = len(SIMULATION_YEARS)
    windows = []
    for start_idx in range(n):
        if start_idx + years > n:
            break  # only full, non-wrapping windows count as real history
        window_years = SIMULATION_YEARS[start_idx:start_idx + years]
        returns = [SP500_ANNUAL_RETURNS[y] for y in window_years]
        success = _simulate_withdrawal_sequence(balance, s["withdrawal_rate_pct"], s["inflation_pct"], returns)
        windows.append({"start_year": window_years[0], "success": success})
    successes = sum(1 for w in windows if w["success"])
    worst = next((w for w in windows if not w["success"]), None)
    return {
        "windows_tested": len(windows),
        "years_simulated": years,
        "success_rate_pct": round(successes / len(windows) * 100, 1) if windows else None,
        "worst_starting_year": worst["start_year"] if worst else None,
    }


def regime_switching(s: dict, trials: int = 1000, seed: int | None = 42) -> dict:
    """Classifies each bundled historical year into one of two regimes —
    "growth" (return >= 0) or "recession" (return < 0) — estimates a
    simple two-state Markov transition matrix from how often the real
    historical sequence actually switched between them, then simulates
    trials where each year's return is drawn from ITS REGIME's own
    mean/stdev, with the regime itself evolving via the estimated
    transition probabilities. Directly comparable to monte_carlo()'s
    single-distribution result — the gap between the two shows how much
    regime persistence (bad years clustering together) matters."""
    rng = random.Random(seed)
    years_list = SIMULATION_YEARS
    rets = [SP500_ANNUAL_RETURNS[y] for y in years_list]
    regimes = ["growth" if r >= 0 else "recession" for r in rets]

    growth_rets = [r for r, g in zip(rets, regimes) if g == "growth"]
    recession_rets = [r for r, g in zip(rets, regimes) if g == "recession"]
    stats = {
        "growth": (statistics.mean(growth_rets), statistics.pstdev(growth_rets) or 1.0),
        "recession": (statistics.mean(recession_rets), statistics.pstdev(recession_rets) or 1.0),
    }

    transitions = {"growth": {"growth": 0, "recession": 0}, "recession": {"growth": 0, "recession": 0}}
    for i in range(len(regimes) - 1):
        transitions[regimes[i]][regimes[i + 1]] += 1
    trans_prob = {}
    for state, counts in transitions.items():
        total = sum(counts.values()) or 1
        trans_prob[state] = {k: v / total for k, v in counts.items()}

    balance = balance_at_retirement(s)
    years = max(1, int(round(years_in_retirement(s))))
    successes = 0
    for _ in range(trials):
        regime = regimes[-1]  # start from the most recently observed regime
        trial_returns = []
        for _ in range(years):
            p_growth = trans_prob[regime]["growth"]
            regime = "growth" if rng.random() < p_growth else "recession"
            mean, stdev = stats[regime]
            trial_returns.append(rng.gauss(mean, stdev))
        if _simulate_withdrawal_sequence(balance, s["withdrawal_rate_pct"], s["inflation_pct"], trial_returns):
            successes += 1

    return {
        "trials": trials,
        "years_simulated": years,
        "success_rate_pct": round(successes / trials * 100, 1),
        "growth_mean_return_pct": round(stats["growth"][0], 2),
        "recession_mean_return_pct": round(stats["recession"][0], 2),
        # Flattened rather than nested (every other model's result dict is
        # flat too, and the frontend's generic RetirementModelCard renderer
        # infers formatting from each key's own name — a nested dict would
        # need its inner keys to carry the same hints, which "growth"/
        # "recession" alone don't). The other two transitions are each
        # this pair's complement (prob_growth_to_recession = 100 -
        # prob_growth_to_growth), so these two numbers are the whole matrix.
        "prob_stay_in_growth_pct": round(trans_prob["growth"]["growth"] * 100, 1),
        "prob_recover_from_recession_pct": round(trans_prob["recession"]["growth"] * 100, 1),
    }
