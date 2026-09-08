"""
retirement_engine.py — assembles every model across
retirement_deterministic.py / retirement_simulation.py /
retirement_guardrails.py / retirement_actuarial.py /
retirement_structuring.py into one ordered, categorized list for the
Retirement Planning tab (2026-08-02, user-specified: all 7 categories,
~26 models total).

Each model function takes retirement_settings.get_settings()'s dict and
returns a small plain result dict — this module just wraps each in a
uniform {key, label, category, description, result} envelope so the
frontend can render a consistent card per model without knowing anything
about what's actually inside `result`.
"""

from dataclasses import dataclass
from typing import Callable

import retirement_actuarial as actuarial
import retirement_deterministic as det
import retirement_guardrails as guardrails
import retirement_simulation as sim
import retirement_structuring as structuring


@dataclass
class RetirementModel:
    key: str
    label: str
    category: str
    description: str
    compute: Callable[[dict], dict]
    caveat: str | None = None


CATEGORIES: tuple[str, ...] = (
    "Non-Probabilistic & Deterministic Models",
    "Probabilistic & Stochastic Simulations",
    "Static Withdrawal Rate Frameworks",
    "Dynamic & Variable Withdrawal Guardrails",
    "Actuarial & Longevity-Linked Models",
    "Liability and Asset Structuring Frameworks",
    "Early Retirement (FIRE) Variations",
)

_DATA_CAVEAT = (
    "Uses a bundled, memory-recalled approximation of historical S&P 500 returns (not a live/audited "
    "dataset) — good for illustrating how this technique behaves, not for precision. See retirement_data.py."
)

MODELS: tuple[RetirementModel, ...] = (
    # ---- 1. Non-Probabilistic & Deterministic Models
    RetirementModel(
        "straight_line_compounding", "Straight-Line Compounding Model", CATEGORIES[0],
        "Assumes a static, unchanging rate of return and inflation across both accumulation and retirement.",
        det.straight_line_compounding,
    ),
    RetirementModel(
        "variable_return_single_sequence", "Variable Return Model", CATEGORIES[0],
        "Evaluates one specific sequence of changing historical returns, walked once (no randomized trials).",
        det.variable_return_single_sequence,
        caveat=_DATA_CAVEAT,
    ),
    RetirementModel(
        "capital_utilization", "Capital Utilization Model", CATEGORIES[0],
        "Solves the constant annual spending that exhausts the portfolio to exactly zero at life expectancy.",
        det.capital_utilization,
    ),
    RetirementModel(
        "capital_preservation", "Capital Preservation Model", CATEGORIES[0],
        "Spends only the portfolio's generated yield, leaving the initial nominal principal untouched.",
        det.capital_preservation,
        caveat="Preserves nominal principal only — inflation still erodes its real purchasing power over time.",
    ),
    # ---- 2. Probabilistic & Stochastic Simulations
    RetirementModel(
        "monte_carlo", "Monte Carlo Simulation", CATEGORIES[1],
        "Runs thousands of randomized annual-return trials (drawn from a normal distribution) to find a success rate.",
        sim.monte_carlo,
        caveat=_DATA_CAVEAT,
    ),
    RetirementModel(
        "bootstrapping", "Bootstrapping (Resampling)", CATEGORIES[1],
        "Randomly draws actual historical years of market data WITH replacement to build synthetic return sequences.",
        sim.bootstrapping,
        caveat=_DATA_CAVEAT,
    ),
    RetirementModel(
        "historical_simulation", "Historical Simulation (Backtesting)", CATEGORIES[1],
        "Tests the plan against every real, uninterrupted historical window the bundled data can cover.",
        sim.historical_simulation,
        caveat=_DATA_CAVEAT + " Only 44 years of data are bundled, so this covers far fewer distinct eras than a real multi-century backtest would.",
    ),
    RetirementModel(
        "regime_switching", "Regime-Switching Models", CATEGORIES[1],
        "Simulates shifting between growth and recession regimes, estimated from how the bundled historical data actually transitioned.",
        sim.regime_switching,
        caveat=_DATA_CAVEAT + " The 2-state (growth/recession) classification is a simplification of real regime-detection models.",
    ),
    # ---- 3. Static Withdrawal Rate Frameworks
    RetirementModel(
        "four_percent_rule", "The 4% Rule", CATEGORIES[2],
        "Withdraws the target rate of the initial portfolio value in year one, adjusting every later year for inflation only.",
        det.four_percent_rule,
    ),
    RetirementModel(
        "rule_of_25", "The Rule of 25", CATEGORIES[2],
        "Total savings target = desired annual retirement spending x 25 (the algebraic inverse of a 4% withdrawal rate).",
        det.rule_of_25,
    ),
    RetirementModel(
        "constant_percentage", "Constant Percentage Method", CATEGORIES[2],
        "Withdraws a fixed percentage of the REMAINING balance each year, so spending fluctuates naturally with the market.",
        det.constant_percentage,
    ),
    # ---- 4. Dynamic & Variable Withdrawal Guardrails
    RetirementModel(
        "guyton_klinger", "Guyton-Klinger Rules", CATEGORIES[3],
        "Explicit \"Capital Preservation\" and \"Prosperity\" guardrails cut or raise spending 10% when the withdrawal rate drifts too far from its starting point.",
        guardrails.guyton_klinger,
    ),
    RetirementModel(
        "vpw", "Variable Percentage Withdrawal (VPW)", CATEGORIES[3],
        "Combines the current balance with remaining life expectancy so the withdrawal PERCENTAGE mechanically rises as the retiree ages.",
        guardrails.variable_percentage_withdrawal,
    ),
    RetirementModel(
        "bengen_floor_ceiling", "Bengen's Floor-and-Ceiling Method", CATEGORIES[3],
        "Sets a rigid maximum ceiling and minimum floor on inflation-adjusted annual spending to prevent extreme volatility.",
        guardrails.bengen_floor_ceiling,
    ),
    RetirementModel(
        "ratchet_rule", "Ratchet Rule", CATEGORIES[3],
        "Spending increases during bull runs but locks in the new higher floor, so it never decreases in a later down market.",
        guardrails.ratchet_rule,
    ),
    RetirementModel(
        "optimal_control_bellman", "Optimal Control Theory", CATEGORIES[3],
        "Uses dynamic-programming optimization (a Bellman equation backward induction) to maximize lifetime consumption utility.",
        guardrails.optimal_control_bellman,
        caveat="Simplified: solved against one constant assumed return (deterministic), not a full stochastic dynamic program over a real return distribution.",
    ),
    # ---- 5. Actuarial & Longevity-Linked Models
    RetirementModel(
        "life_expectancy_method", "Life Expectancy Method", CATEGORIES[4],
        "Divides the current portfolio balance by remaining statistical life expectancy.",
        actuarial.life_expectancy_method,
    ),
    RetirementModel(
        "irs_rmd", "IRS RMD Math", CATEGORIES[4],
        "Uses the IRS Uniform Lifetime Table to compute mandatory minimum withdrawal amounts by age.",
        actuarial.irs_rmd_schedule,
        caveat="Illustrative approximation of the IRS table — verify against current IRS Pub. 590-B for real RMD compliance.",
    ),
    RetirementModel(
        "gompertz_makeham", "Gompertz-Makeham Longevity Function", CATEGORIES[4],
        "A mortality hazard formula (mu(x) = A + B*c^x) used to estimate survival probability and an implied median lifespan.",
        actuarial.gompertz_makeham,
        caveat="Illustrative mortality parameters, not fit to any verified population dataset.",
    ),
    # ---- 6. Liability and Asset Structuring Frameworks
    RetirementModel(
        "asset_liability_matching", "Asset-Liability Matching (ALM)", CATEGORIES[5],
        "Matches guaranteed income (Social Security, pension) against fixed living costs; the portfolio only has to fund the gap.",
        structuring.asset_liability_matching,
    ),
    RetirementModel(
        "time_segmented_bucketing", "Time-Segmented Bucketing", CATEGORIES[5],
        "Segregates the portfolio into chronological tiers — cash for years 1-5, bonds for 6-10, equities for 11+.",
        structuring.time_segmented_bucketing,
    ),
    RetirementModel(
        "bond_ladder", "Bond Ladder Mathematics", CATEGORIES[5],
        "Calculates structural maturity rungs and coupon yield to provide guaranteed annual cash flow.",
        structuring.bond_ladder,
    ),
    # ---- 7. Early Retirement (FIRE) Variations
    RetirementModel(
        "lean_fire", "LeanFIRE Math", CATEGORIES[6],
        "Solves for a savings target based on minimal, bare-bones survival expenses.",
        det.lean_fire,
    ),
    RetirementModel(
        "fat_fire", "FatFIRE Math", CATEGORIES[6],
        "Solves for an expanded savings target based on an affluent lifestyle with high discretionary spending.",
        det.fat_fire,
    ),
    RetirementModel(
        "coast_fire", "CoastFIRE Math", CATEGORIES[6],
        "The net worth needed today so pure compounding alone reaches the traditional retirement target by retirement age.",
        det.coast_fire,
    ),
    RetirementModel(
        "barista_fire", "BaristaFIRE Math", CATEGORIES[6],
        "The portfolio bridge needed to cover lifestyle gaps while working a lower-stress, part-time job.",
        det.barista_fire,
    ),
)


def compute_all(settings: dict) -> list[dict]:
    results = []
    for model in MODELS:
        try:
            result = model.compute(settings)
        except (ZeroDivisionError, ValueError):
            result = {"error": "Could not compute with the current settings (check for zero/invalid inputs)."}
        results.append({
            "key": model.key,
            "label": model.label,
            "category": model.category,
            "description": model.description,
            "caveat": model.caveat,
            "result": result,
        })
    return results
