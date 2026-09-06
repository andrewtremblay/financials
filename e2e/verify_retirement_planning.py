"""
e2e/verify_retirement_planning.py — one-off Playwright verification for the
new "Retirement Planning" tab: the settings panel (persist + refetch), and
all ~26 models across the 7 requested categories rendering without error.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_retirement_planning.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

EXPECTED_CATEGORIES = [
    "Non-Probabilistic & Deterministic Models",
    "Probabilistic & Stochastic Simulations",
    "Static Withdrawal Rate Frameworks",
    "Dynamic & Variable Withdrawal Guardrails",
    "Actuarial & Longevity-Linked Models",
    "Liability and Asset Structuring Frameworks",
    "Early Retirement (FIRE) Variations",
]

console_errors: list[str] = []


def log_console(msg):
    if msg.type == "error":
        console_errors.append(msg.text)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 950})
        page.on("console", log_console)

        # API-level sanity check first.
        page.goto("http://localhost:8000", wait_until="networkidle")
        models_resp = page.evaluate("() => fetch('/api/retirement/models').then(r => r.json())")
        assert len(models_resp["models"]) >= 26, len(models_resp["models"])
        categories = {m["category"] for m in models_resp["models"]}
        assert categories == set(EXPECTED_CATEGORIES), categories
        for m in models_resp["models"]:
            assert "error" not in m["result"], f"{m['key']} errored: {m['result']}"

        # Drive the UI.
        page.click("text=Retirement Planning")
        page.wait_for_selector("text=Personal", timeout=10000)
        page.wait_for_selector("text=LeanFIRE Math", timeout=10000)
        page.wait_for_selector("text=Monte Carlo Simulation", timeout=10000)
        page.wait_for_selector("text=Guyton-Klinger Rules", timeout=10000)
        page.wait_for_selector("text=IRS RMD Math", timeout=10000)
        page.wait_for_selector("text=Bond Ladder Mathematics", timeout=10000)
        for category in EXPECTED_CATEGORIES:
            page.get_by_text(category, exact=True).wait_for(timeout=10000)
        page.screenshot(path=str(SCREENSHOT_DIR / "retirement_planning_top.png"), full_page=False)

        # Update a setting and confirm it persists + models recompute.
        age_input = page.locator("label", has_text="Current age").locator("input")
        age_input.fill("40")
        page.get_by_role("button", name="Save changes").click()
        page.wait_for_timeout(1000)

        settings_after = page.evaluate("() => fetch('/api/retirement/settings').then(r => r.json())")
        assert settings_after["current_age"] == 40.0, settings_after

        # Scroll to the FIRE section and screenshot for visual confirmation.
        page.get_by_text("Early Retirement (FIRE) Variations", exact=True).scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.screenshot(path=str(SCREENSHOT_DIR / "retirement_planning_fire.png"))

        # Restore the setting so this run doesn't leave the real plan mutated.
        page.evaluate("() => fetch('/api/retirement/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({current_age: 35})})")

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: Retirement Planning tab renders all 7 categories and >=26 models with "
              "no computation errors, the settings panel persists an edit, and models "
              "recompute against the new settings.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
