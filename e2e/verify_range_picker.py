"""
e2e/verify_range_picker.py — one-off Playwright verification for the new
rolling lookback window picker (1M/3M/6M/1Y/YTD), RangePicker.tsx wired
into BudgetDashboard.tsx alongside the existing MonthPicker.

Not part of the permanent e2e/visual_check.py flow -- this specifically
drives the 5 range buttons, confirms the sidebar totals/Sankey diagram
update, confirms single-month mode still works, and confirms the URL
picks up ?range=. Screenshots land in e2e/screenshots/, prefixed range_.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_range_picker.py
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

console_errors: list[str] = []
page_errors: list[str] = []


def log_console(msg):
    if msg.type == "error":
        console_errors.append(msg.text)


def log_page_error(exc):
    page_errors.append(str(exc))


def net_line(page) -> str:
    """The header sub-line: "Net $X · Income $Y · Expenses $Z"."""
    return page.locator("p.text-xs.text-gray-500.mt-0\\.5.truncate").first.inner_text()


def parse_income(text: str) -> float:
    m = re.search(r"Income\s+\$?(-?[\d,]+)", text)
    return float(m.group(1).replace(",", "")) if m else 0.0


def main():
    base = "http://localhost:8000"
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", log_console)
        page.on("pageerror", log_page_error)

        print("=== Loading dashboard (single-month/default mode) ===")
        page.goto(base, wait_until="networkidle")
        page.wait_for_selector("text=Budget Dashboard", timeout=10000)
        page.wait_for_timeout(600)

        range_group = page.locator('[aria-label="Time range"]')
        if range_group.count() == 0:
            failures.append("RangePicker (role=group, aria-label='Time range') not found on page")
            print("FATAL: cannot continue without the range picker")
        else:
            single_income_text = net_line(page)
            single_income = parse_income(single_income_text)
            print(f"Single-month (default) income line: {single_income_text!r} -> {single_income}")
            page.screenshot(path=str(SCREENSHOT_DIR / "range_00_single_month_default.png"))

            # "1M" pill should be visually active by default (single mode).
            one_m_btn = range_group.locator('button:has-text("1M")')
            if one_m_btn.get_attribute("aria-pressed") != "true":
                failures.append("'1M' pill is not aria-pressed=true by default (should represent single-month mode)")

            results = {}
            for label in ["3M", "6M", "1Y", "YTD"]:
                print(f"\n=== Selecting range: {label} ===")
                btn = range_group.locator(f'button:has-text("{label}")')
                btn.click()
                page.wait_for_timeout(700)
                if btn.get_attribute("aria-pressed") != "true":
                    failures.append(f"{label} pill did not become aria-pressed=true after click")
                url = page.url
                if f"range={label}" not in url:
                    failures.append(f"URL did not pick up ?range={label} after clicking {label} (got {url})")
                income_text = net_line(page)
                income = parse_income(income_text)
                results[label] = income
                print(f"{label} income line: {income_text!r} -> {income}")

                # Sankey diagram should have rendered flows (not the "No
                # flow data" empty state) for a range with real data.
                empty_state = page.locator("text=No flow data for this period")
                if empty_state.count() > 0:
                    failures.append(f"{label} range shows the empty Sankey state -- expected real flow data")

                page.screenshot(path=str(SCREENSHOT_DIR / f"range_01_{label}.png"))

            print("\n=== Sanity: longer ranges should generally show more cumulative income ===")
            print("Results:", {k: v for k, v in results.items()})
            if not (results["3M"] <= results["6M"] <= results["1Y"]):
                failures.append(f"Expected monotonically non-decreasing income 3M<=6M<=1Y, got {results}")
            if not (single_income <= results["3M"]):
                failures.append(f"Expected 3M income ({results['3M']}) >= single month ({single_income})")

            print("\n=== Switching back to single-month mode (the '1M' pill) ===")
            one_m_btn.click()
            page.wait_for_timeout(700)
            if one_m_btn.get_attribute("aria-pressed") != "true":
                failures.append("'1M' pill did not become aria-pressed=true after switching back")
            url_after_single = page.url
            if "range=" in url_after_single:
                failures.append(f"URL still has ?range= after switching back to single-month mode (got {url_after_single})")
            back_income_text = net_line(page)
            back_income = parse_income(back_income_text)
            print(f"Back to single-month income line: {back_income_text!r} -> {back_income}")
            if abs(back_income - single_income) > 0.01:
                failures.append(f"Single-month income after round-trip ({back_income}) != original ({single_income})")
            page.screenshot(path=str(SCREENSHOT_DIR / "range_02_back_to_single.png"))

            print("\n=== Bookmarked range URL restores correctly on fresh load ===")
            month_param = re.search(r"month=([0-9]{4}-[0-9]{2})", url_after_single)
            anchor = month_param.group(1) if month_param else None
            if anchor:
                bookmark_url = f"{base}/?month={anchor}&range=6M"
                page.goto(bookmark_url, wait_until="networkidle")
                page.wait_for_selector("text=Budget Dashboard", timeout=10000)
                page.wait_for_timeout(700)
                restored_btn = range_group.locator('button:has-text("6M")')
                if restored_btn.get_attribute("aria-pressed") != "true":
                    failures.append("Reloading a ?range=6M URL directly did not restore 6M mode")
                page.screenshot(path=str(SCREENSHOT_DIR / "range_03_bookmarked_6m_reload.png"))
            else:
                failures.append("Could not extract ?month= from URL to test bookmark restore")

        browser.close()

    print(f"\nScreenshots written to {SCREENSHOT_DIR}")
    print("\n=== Console errors ===")
    for e in console_errors:
        print("  ", e)
    print("=== Page errors (uncaught exceptions) ===")
    for e in page_errors:
        print("  ", e)

    print("\n=== Failures ===")
    for f in failures:
        print("  FAIL:", f)

    if console_errors or page_errors or failures:
        print("\nFAIL")
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
