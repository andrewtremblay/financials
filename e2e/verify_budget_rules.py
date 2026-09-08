"""
e2e/verify_budget_rules.py — one-off Playwright verification for the new
"Budget Rules" tab: 50/30/20, 28/36, 70/20/10, and 80/20 rule cards, the
enable/disable toggle bar, and the Budget Classification settings panel.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_budget_rules.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

console_errors: list[str] = []


def log_console(msg):
    if msg.type == "error":
        console_errors.append(msg.text)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", log_console)

        # Sanity-check the raw API responses first, independent of the UI.
        page.goto("http://localhost:8000", wait_until="networkidle")
        rules_resp = page.evaluate("() => fetch('/api/months/2026-07/budget-rules').then(r => r.json())")
        rule_keys = {r["key"] for r in rules_resp["rules"]}
        assert rule_keys == {"50_30_20", "28_36", "70_20_10", "80_20"}, rule_keys
        rule_50_30_20 = next(r for r in rules_resp["rules"] if r["key"] == "50_30_20")
        assert {s["key"] for s in rule_50_30_20["segments"]} == {"need", "want", "savings"}
        rule_28_36 = next(r for r in rules_resp["rules"] if r["key"] == "28_36")
        assert rule_28_36["caveat"] and "gross" in rule_28_36["caveat"].lower()

        classification_resp = page.evaluate("() => fetch('/api/budget-classification').then(r => r.json())")
        groceries = next(c for c in classification_resp if c["section"] == "DAILY LIVING" and c["label"] == "Groceries")
        assert groceries["budget_type"] == "need"
        mortgage = next(c for c in classification_resp if c["label"] == "Mortgage (12 Warren)")
        assert mortgage["housing"] is True and mortgage["debt"] is True

        # Now drive the actual UI.
        page.click("text=Budget Rules")
        page.wait_for_selector("text=50/30/20", timeout=10000)
        page.wait_for_selector("text=28/36", timeout=10000)
        page.wait_for_selector("text=70/20/10", timeout=10000)
        page.wait_for_selector("text=80/20", timeout=10000)
        page.screenshot(path=str(SCREENSHOT_DIR / "budget_rules_tab.png"))

        # Toggle 28/36 off and confirm its card disappears.
        page.get_by_role("checkbox").filter(has=page.locator("xpath=..", has_text="28/36")).first
        checkbox_28_36 = page.locator("label", has_text="28/36").locator("input[type=checkbox]")
        checkbox_28_36.uncheck()
        page.wait_for_timeout(200)
        assert page.locator("h3", has_text="28/36").count() == 0, "28/36 card should be hidden after unchecking"
        checkbox_28_36.check()
        page.wait_for_timeout(200)
        assert page.locator("h3", has_text="28/36").count() == 1, "28/36 card should reappear after re-checking"

        # Open the classification settings panel and flip one item, then
        # confirm the change is reflected in a fresh GET (and restore it).
        page.get_by_role("button", name="Edit Need/Want classification").click()
        panel = page.get_by_role("dialog").filter(has_text="Budget Classification")
        panel.wait_for(timeout=10000)
        groceries_row = panel.locator("div", has_text="Groceries").last
        groceries_select = groceries_row.locator("select")
        groceries_select.wait_for(timeout=5000)
        assert groceries_select.input_value() == "need"
        page.screenshot(path=str(SCREENSHOT_DIR / "budget_classification_panel.png"))

        groceries_select.select_option("want")
        page.wait_for_timeout(500)
        after_edit = page.evaluate("() => fetch('/api/budget-classification').then(r => r.json())")
        edited = next(c for c in after_edit if c["section"] == "DAILY LIVING" and c["label"] == "Groceries")
        assert edited["budget_type"] == "want"

        # Restore the default so this verification run doesn't leave the
        # real classification store mutated.
        groceries_select.select_option("need")
        page.wait_for_timeout(500)
        restored = page.evaluate("() => fetch('/api/budget-classification').then(r => r.json())")
        restored_entry = next(c for c in restored if c["section"] == "DAILY LIVING" and c["label"] == "Groceries")
        assert restored_entry["budget_type"] == "need"

        panel.get_by_role("button", name="×").click()

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: Budget Rules tab renders all 4 rules with correct segments/caveat, "
              "the enable/disable toggle works, and the classification settings panel "
              "reads/writes overrides correctly.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
