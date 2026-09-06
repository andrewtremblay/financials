"""
retirement_settings.py — the shared assumptions every model in
retirement_deterministic.py / retirement_guardrails.py /
retirement_actuarial.py / retirement_structuring.py /
retirement_simulation.py is computed from: current age, target retirement
age, portfolio balance, return/inflation assumptions, and spending targets.

A single persisted object (not a list of dated overrides, unlike
overrides.py/custom_categories.py/untracked_income.py) — there's only ever
one "current plan," edited in place via the Retirement Planning tab's
settings panel.

Portfolio balance, income, and savings figures here are all MANUAL fields
for now — this app only ever calls Plaid's /transactions/sync, never
/accounts/balance or /investments/holdings, so there's no live balance to
pull yet. Wiring that up is a real, separate integration — tracked as a
future TODO, not built here (2026-08-02, user-specified: ship the manual
version now, Plaid balance integration later).
"""

import json
from pathlib import Path

RETIREMENT_SETTINGS_FILE = Path("retirement_settings.json")

DEFAULT_SETTINGS = {
    "current_age": 35.0,
    "retirement_age": 65.0,
    "life_expectancy_age": 90.0,
    "current_portfolio_balance": 0.0,
    "annual_savings": 0.0,  # current annual contribution toward the portfolio, pre-retirement
    "annual_return_pct": 7.0,  # nominal expected portfolio return, %
    "inflation_pct": 3.0,  # %
    "bond_yield_pct": 4.0,  # assumed fixed-income yield, for bond-ladder/ALM math
    "withdrawal_rate_pct": 4.0,  # for the 4% Rule / Rule of 25 / CoastFIRE
    "desired_annual_spending": 0.0,  # retirement-year spending target, today's dollars
    "lean_annual_spending": 0.0,  # LeanFIRE target base
    "fat_annual_spending": 0.0,  # FatFIRE target base
    "barista_annual_spending_gap": 0.0,  # BaristaFIRE: portfolio-funded gap after part-time income covers the rest
    "social_security_annual": 0.0,  # ALM floor income
    "pension_annual": 0.0,  # ALM floor income
    "risk_aversion": 3.0,  # CRRA gamma, for the Optimal Control Theory model
}


def _load() -> dict:
    if not RETIREMENT_SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    with open(RETIREMENT_SETTINGS_FILE) as f:
        data = json.load(f)
    # Merge over defaults rather than trust the file's own key set — lets
    # DEFAULT_SETTINGS grow (new fields) without needing a migration step.
    return {**DEFAULT_SETTINGS, **data}


def get_settings() -> dict:
    return _load()


def update_settings(patch: dict) -> dict:
    unknown = set(patch) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ValueError(f"unknown setting(s): {sorted(unknown)}")
    data = _load()
    data.update(patch)
    with open(RETIREMENT_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return data
