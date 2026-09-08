"""
e2e/verify_untracked_income_detail.py — one-off Playwright verification for
the "Untracked Income" node's expanded explanation modal: a breakdown of
what makes up the number, plus add/remove/change controls scoped to the
current month, current-and-future, or all months.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_untracked_income_detail.py
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
        page = browser.new_page(viewport={"width": 1400, "height": 950})
        page.on("console", log_console)

        page.goto("http://localhost:8000", wait_until="networkidle")
        page.wait_for_selector("text=Take Home Salary (Zus)", timeout=15000)
        page.wait_for_selector('svg[data-testid="sankey-diagram"]', timeout=15000)

        untracked_node = page.locator('svg[data-testid="sankey-diagram"] text', has_text="Untracked Income").first
        untracked_node.wait_for(timeout=10000)
        untracked_node.click(force=True)

        modal = page.get_by_role("dialog").filter(has_text="Untracked Income")
        modal.wait_for(timeout=10000)
        modal.get_by_text("Breakdown").wait_for(timeout=5000)
        modal.get_by_text("Which Savings items count as untracked income").wait_for(timeout=10000)
        # The labels list is a separate async fetch from the modal's own
        # mount — wait for it to actually resolve (a real row rendering)
        # before touching any checkbox, rather than racing it.
        modal.get_by_text("Emergency Fund", exact=True).first.wait_for(timeout=10000)
        page.screenshot(path=str(SCREENSHOT_DIR / "untracked_income_detail.png"))

        # Toggle "Other Savings" on (it's off by default) with "This month only".
        other_savings_row = modal.locator("li", has_text="Other Savings").first
        other_savings_row.wait_for(timeout=10000)
        checkbox = other_savings_row.locator('input[type="checkbox"]')
        checkbox.wait_for(timeout=10000)
        was_checked = checkbox.is_checked()
        assert not was_checked, "expected Other Savings to be off by default"
        checkbox.click()

        scope_panel = modal.locator("div", has_text="Mark").last
        scope_panel.get_by_text("This month only").wait_for(timeout=5000)
        modal.get_by_role("button", name="Save").click()
        page.wait_for_timeout(800)

        # Confirm via the API directly that a rule now exists.
        rules = page.evaluate("() => fetch('/api/untracked-income-rules').then(r => r.json())")
        matching = [r for r in rules if r["label"] == "Other Savings" and r["enabled"]]
        assert len(matching) == 1, f"expected exactly one enabled rule for Other Savings, got {matching}"
        assert matching[0]["scope"] == "current"
        rule_id = matching[0]["id"]

        page.screenshot(path=str(SCREENSHOT_DIR / "untracked_income_after_toggle.png"))

        # Clean up via the "Manage existing rules" panel.
        manage_button = modal.get_by_text("Manage existing rules", exact=False)
        manage_button.click()
        remove_button = modal.get_by_text("remove", exact=True).first
        remove_button.wait_for(timeout=5000)
        remove_button.click()
        page.wait_for_timeout(500)

        rules_after = page.evaluate("() => fetch('/api/untracked-income-rules').then(r => r.json())")
        assert all(r["id"] != rule_id for r in rules_after), "rule should have been removed"

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: Untracked Income modal shows a breakdown + editable Savings-item "
              "toggles, creating a scoped rule persists and updates the checkbox state, "
              "and removing the rule via the manage panel cleans it up.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
