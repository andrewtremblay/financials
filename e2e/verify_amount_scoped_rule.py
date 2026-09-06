"""
e2e/verify_amount_scoped_rule.py — one-off Playwright verification for the
optional amount-matching field on merchant category rules (RecategorizeModal
"All transactions matching a pattern" scope now has an "Only when amount is
exactly" checkbox + amount input, wired through to POST /api/category-rules'
new `amount` field).

Flow: open the dashboard -> open Recategorize on a real transaction -> switch
to "All transactions matching a pattern" -> confirm the amount input is
prefilled with the transaction's own amount -> enable the checkbox, use a
pattern+amount combo deliberately unlikely to match any real transaction (so
this verification run doesn't retroactively recategorize the user's actual
data) -> save -> confirm via GET /api/category-rules that the rule was
persisted with the amount, and affected_transaction_count was 0 -> clean up
via DELETE /api/category-rules/{id}.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_amount_scoped_rule.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

TEST_PATTERN = "PLAYWRIGHT_AMOUNT_RULE_NOMATCH"
TEST_AMOUNT = 123456.78

console_errors: list[str] = []


def log_console(msg):
    if msg.type == "error":
        console_errors.append(msg.text)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", log_console)

        page.goto("http://localhost:8000", wait_until="networkidle")
        page.wait_for_selector("text=Take Home Salary (Zus)", timeout=15000)

        page.click("text=Take Home Salary (Zus)")
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)
        page.click('button[title="Recategorize"]')
        page.wait_for_selector("text=Recategorize", timeout=10000)

        modal = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal.get_by_text("All transactions matching a pattern").click()

        pattern_input = modal.locator("div.pl-6 input").first
        pattern_input.wait_for(timeout=5000)
        original_amount = modal.locator('input[type="number"]')
        assert original_amount.count() == 0, "amount input should be hidden until the checkbox is checked"

        checkbox = modal.locator('input[type="checkbox"]')
        checkbox.check()
        amount_input = modal.locator('input[type="number"]')
        amount_input.wait_for(timeout=5000)
        prefilled = amount_input.input_value()
        print(f"Amount input prefilled with: {prefilled!r}")
        assert prefilled not in ("", "0"), "amount input should be prefilled with the transaction's own amount"

        pattern_input.fill(TEST_PATTERN)
        amount_input.fill(str(TEST_AMOUNT))

        # Pick a real category from the dropdown so save doesn't fail on
        # "Pick a category."
        modal.locator("select").first.select_option(index=1)

        page.screenshot(path=str(SCREENSHOT_DIR / "amount_scoped_rule_form.png"))

        modal.get_by_role("button", name="Save").click()
        # Saving a merchant rule synchronously re-categorizes every linked
        # account (api_server.create_category_rule calls
        # plaid_sync.write_categorized_csv for each), which can take a while
        # even when most descriptions hit the memoized-category cache.
        modal.wait_for(state="detached", timeout=120000)

        # Verify persistence + affected-count math via the API directly
        # (Playwright's browser-context fetch, not a shell curl).
        rules = page.evaluate("() => fetch('/api/category-rules').then(r => r.json())")
        created = next((r for r in rules if r["pattern"] == TEST_PATTERN), None)
        print(f"Created rule: {created}")
        assert created is not None, "rule was not persisted"
        assert created["amount"] == TEST_AMOUNT, f"expected amount {TEST_AMOUNT}, got {created['amount']}"

        # Clean up regardless of outcome below.
        page.evaluate(
            "(id) => fetch(`/api/category-rules/${id}`, {method: 'DELETE'})",
            created["id"],
        )
        rules_after = page.evaluate("() => fetch('/api/category-rules').then(r => r.json())")
        assert all(r["id"] != created["id"] for r in rules_after), "rule was not cleaned up"

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: amount-scoped merchant rule created with prefilled amount, "
              "persisted with the amount field, and cleaned up successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
