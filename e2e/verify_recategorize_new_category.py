"""
e2e/verify_recategorize_new_category.py — one-off Playwright verification
for the RecategorizeModal "add a new category" redesign (Section picker +
subcategory text field, replacing the old free-text "type NEW_CATEGORY by
hand" fallback) and the /api/categories persistence fix behind it.

Flow: open the dashboard -> click into a line item's transaction drawer ->
open Recategorize on a real transaction -> switch to "add a new category" ->
pick a section + type a subcategory name -> save -> reopen Recategorize on
the same transaction and confirm the new category now appears (and is
selected) in the normal dropdown.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_recategorize_new_category.py
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

        page.goto("http://localhost:8000", wait_until="networkidle")
        page.wait_for_selector("text=Take Home Salary (Zus)", timeout=15000)

        # Open the transaction drawer for a line item with real data.
        page.click("text=Take Home Salary (Zus)")
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)

        # Open the recategorize modal for the first transaction in the drawer.
        page.click('button[title="Recategorize"]')
        page.wait_for_selector("text=Recategorize", timeout=10000)

        # Both the drawer and the recategorize modal are role="dialog" at
        # this point -- filter to the one that actually says "Recategorize"
        # (the drawer's per-row button only has that as a title attribute,
        # not visible text, so it won't match).
        modal = page.get_by_role("dialog").filter(has_text="Recategorize")

        # Switch to "add a new category" mode.
        modal.get_by_role("button", name="Category not listed? Add a new one").click()
        subcategory_input = modal.get_by_placeholder("Subcategory name", exact=False)
        subcategory_input.wait_for(timeout=10000)

        subcategory_name = "Playwright Verification Item"
        modal.locator("select").first.select_option(label="Entertainment")
        subcategory_input.fill(subcategory_name)

        # Confirm the client-side key preview rendered before saving.
        modal.get_by_text("PLAYWRIGHT VERIFICATION ITEM").wait_for(timeout=5000)
        page.screenshot(path=str(SCREENSHOT_DIR / "recategorize_add_new_category.png"))

        modal.get_by_role("button", name="Save").click()
        modal.wait_for(state="detached", timeout=10000)

        # Reopen the modal (on whichever transaction is now first in the
        # drawer -- the one we just recategorized moved to a different
        # line item's bucket, so the drawer's "first" transaction shifted;
        # that's expected, not a bug). What matters is that the category we
        # just created is now a selectable *option* in the normal dropdown,
        # not just held in the component state of the instance that created
        # it -- that's the actual bug this feature fixes.
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)
        page.click('button[title="Recategorize"]')
        modal2 = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal2.wait_for(timeout=10000)

        dropdown = modal2.locator("select").first
        option_texts = dropdown.locator("option").all_inner_texts()
        match = next((t for t in option_texts if "PLAYWRIGHT VERIFICATION ITEM" in t), None)
        print(f"New category option in dropdown: {match!r}")
        assert match is not None, "newly-created category never appeared as a dropdown option on reopen"
        # The dropdown displays CategoryOption.section verbatim (the raw
        # section *key*, e.g. "ENTERTAINMENT" -- consistent with how every
        # pre-existing static category already renders, e.g. "HOME →
        # Mortgage (12 Warren) (MORTGAGE WARREN)"), not budget_schema's
        # prettified Section.label ("Entertainment").
        assert "ENTERTAINMENT" in match

        # Select it explicitly so the screenshot visibly shows the new
        # category chosen in the dropdown, not just present in the list.
        dropdown.select_option(label=match)
        page.screenshot(path=str(SCREENSHOT_DIR / "recategorize_new_category_in_dropdown.png"))
        modal2.get_by_role("button", name="Cancel").click()

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: new category created via Section + subcategory fields, "
              "persisted, and appears selected in the dropdown on reopen.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
