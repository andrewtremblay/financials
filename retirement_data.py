"""
retirement_data.py — bundled reference data for retirement_simulation.py
(Monte Carlo / Bootstrapping / Historical Simulation / Regime-Switching) and
retirement_actuarial.py (IRS RMD / Gompertz-Makeham).

DATA QUALITY DISCLAIMER (read before trusting any number downstream of
this file): this app has no internet/live-data access, so nothing here was
fetched from an authoritative source at build time. SP500_ANNUAL_RETURNS is
transcribed from commonly-cited, memory-recalled approximate figures for
S&P 500 total return (price + dividends) by year — good enough to
illustrate how these simulation techniques behave and roughly shaped like
real market history, but NOT a substitute for an audited dataset (e.g.
Aswath Damodaran's NYU Stern historical returns page, or Robert Shiller's
data) if a real decision depends on precision. BOND_ANNUAL_RETURNS is not
even an attempt at historical accuracy — bond total returns are far less
memorable/verifiable from recall than equity returns, so it's a simplified,
clearly-synthetic yield-based approximation instead of presenting
low-confidence numbers as if they were real history. IRS_UNIFORM_LIFETIME_TABE
and the Gompertz-Makeham parameters below are similarly illustrative
approximations of publicly-known tables/figures, not a verified transcription
— always check current IRS Pub. 590-B for real RMD compliance
(2026-08-02, user acknowledged this tradeoff when requesting a bundled
dataset over a live market-data integration).
"""

# Approximate S&P 500 total annual return (%), 1980-2023 — illustrative,
# see module docstring.
SP500_ANNUAL_RETURNS: dict[int, float] = {
    1980: 32.5, 1981: -4.9, 1982: 21.5, 1983: 22.6, 1984: 6.3,
    1985: 31.7, 1986: 18.7, 1987: 5.3, 1988: 16.6, 1989: 31.7,
    1990: -3.1, 1991: 30.5, 1992: 7.6, 1993: 10.1, 1994: 1.3,
    1995: 37.6, 1996: 23.0, 1997: 33.4, 1998: 28.6, 1999: 21.0,
    2000: -9.1, 2001: -11.9, 2002: -22.1, 2003: 28.7, 2004: 10.9,
    2005: 4.9, 2006: 15.8, 2007: 5.5, 2008: -37.0, 2009: 26.5,
    2010: 15.1, 2011: 2.1, 2012: 16.0, 2013: 32.4, 2014: 13.7,
    2015: 1.4, 2016: 12.0, 2017: 21.8, 2018: -4.4, 2019: 31.5,
    2020: 18.4, 2021: 28.7, 2022: -18.1, 2023: 26.3,
}

# Simplified illustrative bond series (NOT historical — see disclaimer
# above): a mild-mean-reverting yield-like sequence, mildly negatively
# correlated with the equity series in its sharpest equity drawdown years
# (roughly consistent with a flight-to-quality pattern), used only to give
# the bond-ladder/ALM/regime models a plausible second asset to work with.
BOND_ANNUAL_RETURNS: dict[int, float] = {
    year: (8.0 if ret < -15 else (-2.0 if ret > 25 else 4.5))
    for year, ret in SP500_ANNUAL_RETURNS.items()
}

SIMULATION_YEARS: list[int] = sorted(SP500_ANNUAL_RETURNS)

# IRS Uniform Lifetime Table (illustrative approximation of the
# post-SECURE-2.0 table) — age -> distribution period (years). RMD =
# account balance / divisor. Ages below 72 aren't subject to RMDs; ages
# above the table's range reuse the final entry.
IRS_UNIFORM_LIFETIME_TABLE: dict[int, float] = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0,
    79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0,
    86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8,
    93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8,
    100: 6.4,
}


def rmd_divisor(age: int) -> float:
    if age < 72:
        return IRS_UNIFORM_LIFETIME_TABLE[72]
    capped_age = min(age, max(IRS_UNIFORM_LIFETIME_TABLE))
    return IRS_UNIFORM_LIFETIME_TABLE[capped_age]


# Gompertz-Makeham mortality hazard parameters: mu(x) = A + B * c^x.
# Illustrative approximations in the ballpark of commonly-published U.S.
# population figures — not fit to any specific cohort or dataset.
GOMPERTZ_MAKEHAM_A = 0.0006  # age-independent ("accident") hazard component
GOMPERTZ_MAKEHAM_B = 0.00004
GOMPERTZ_MAKEHAM_C = 1.096
