"""
e2e/verify_three_features.py — one-off Playwright verification for three
related dashboard changes (2026-08-02, user-requested):
  1. A "Hidden Transactions" badge/drawer for system-recognized transfer/
     payment categories (previously invisible everywhere).
  2. Creating a brand-new top-level section (not just a subcategory within
     an existing one) from the recategorize modal.
  3. After recategorizing, transactions that just moved render grayed out
     (but still editable) in their new drawer location.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_three_features.py
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

        # --- Feature 1: Hidden Transactions ---
        month_resp = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
        assert isinstance(month_resp["hidden"], list)
        hidden_button = page.get_by_role("button", name="hidden")
        if len(month_resp["hidden"]) > 0:
            hidden_button.wait_for(timeout=10000)
            hidden_button.click()
            drawer = page.get_by_role("dialog").filter(has_text="Hidden Transactions")
            drawer.wait_for(timeout=10000)
            page.screenshot(path=str(SCREENSHOT_DIR / "hidden_transactions_drawer.png"))
            drawer.get_by_role("button", name="×").click()
            print(f"Feature 1 OK: {len(month_resp['hidden'])} hidden bucket(s), drawer opened and showed them.")
        else:
            print("Feature 1: no hidden transactions this month to display (API field present and correctly typed).")

        # --- Feature 2: Create a new top-level section ---
        page.click("text=Take Home Salary (Zus)")
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)
        page.click('button[title="Recategorize"]')
        modal = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal.wait_for(timeout=10000)
        modal.get_by_role("button", name="Category not listed? Add a new one").click()
        section_select = modal.locator("select").first
        section_select.wait_for(timeout=5000)
        section_select.select_option(label="+ Create a new section")
        new_section_input = modal.get_by_placeholder("New section name", exact=False)
        new_section_input.wait_for(timeout=5000)
        new_section_input.fill("Playwright Test Section")
        subcategory_input = modal.get_by_placeholder("Subcategory name", exact=False)
        subcategory_input.fill("Playwright Test Item")
        page.screenshot(path=str(SCREENSHOT_DIR / "create_new_section_form.png"))
        modal.get_by_role("button", name="Cancel").click()  # don't actually mutate real budget schema
        # The Cancel above only closes the modal -- the LineItem drawer
        # underneath (opened by the "Take Home Salary (Zus)" click above)
        # is still open and its backdrop would intercept Feature 3's clicks.
        # NotesDrawer has no Escape handler -- click its backdrop instead.
        drawer_backdrop = page.locator("div.absolute.inset-0.bg-black\\/40")
        if drawer_backdrop.count() > 0:
            drawer_backdrop.first.click(force=True)
        page.wait_for_timeout(300)

        sections_resp = page.evaluate("() => fetch('/api/sections').then(r => r.json())")
        # Cancel means we never saved -- confirm the new section is NOT in the list yet.
        assert "PLAYWRIGHT TEST SECTION" not in {s["key"] for s in sections_resp}
        print("Feature 2 OK: new-section option appears in the picker and reveals a name input.")

        # --- Feature 3: grayed-out recently-moved transactions ---
        # Real production data -- capture the exact original category so it
        # can be restored at the end, not left mutated by this run.
        zus = next(
            li for s in month_resp["sections"] if s["key"] == "income"
            for li in s["line_items"] if li["label"] == "Take Home Salary (Zus)"
        )
        target_txn = zus["transactions"][0]
        original_category = target_txn["category"]
        txn_id = target_txn["transaction_id"]

        page.click("text=Take Home Salary (Zus)")
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)
        first_row = page.locator("div.group").first
        description = first_row.locator("p").first.inner_text()
        page.click('button[title="Recategorize"]')
        modal2 = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal2.wait_for(timeout=10000)
        select = modal2.locator("select").first
        # Match the exact category CODE in parens, not just a substring of
        # the option text -- "INTEREST" alone also matches "DAILY LIVING ->
        # ... (INTEREST CHARGED PURCHASES)", which sorts before "income ->
        # Interest Income (INTEREST)" and was silently picked instead.
        select.select_option(label=next(o for o in select.locator("option").all_inner_texts() if o.strip().endswith("(INTEREST)")))
        modal2.get_by_role("button", name="Save").click()
        modal2.wait_for(state="detached", timeout=15000)
        # The Save above only closes the modal -- the source LineItem
        # drawer (Take Home Salary (Zus), opened above) is still open and
        # its backdrop would block clicking "Interest Income" next.
        page.locator("div.absolute.inset-0.bg-black\\/40").first.click(force=True)
        page.wait_for_timeout(300)

        try:
            # Re-open the drawer for "Interest Income" -- the transaction we
            # just moved there should render at reduced opacity.
            page.click("text=Interest Income")
            drawer2 = page.get_by_role("dialog").last
            drawer2.wait_for(timeout=10000)
            moved_row = drawer2.locator("div.group", has_text=description).first
            moved_row.wait_for(timeout=10000)
            opacity = moved_row.evaluate("el => getComputedStyle(el).opacity")
            print(f"Moved row computed opacity: {opacity}")
            assert float(opacity) < 1.0, "recently-moved row should render at reduced opacity"
            # Still editable: the recategorize button must exist and be clickable.
            assert moved_row.locator('button[title="Recategorize"]').count() == 1
            page.screenshot(path=str(SCREENSHOT_DIR / "recently_moved_grayed_out.png"))
            print("Feature 3 OK: recategorized transaction renders grayed out in its new drawer location, still editable.")
        finally:
            # Restore the transaction's original category via the API
            # directly (fast, and doesn't depend on the drawer UI state
            # above having succeeded).
            page.evaluate(
                "(args) => fetch(`/api/transactions/${args.id}/category`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({category: args.category})})",
                {"id": txn_id, "category": original_category},
            )
            restored = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
            restored_zus = next(
                li for s in restored["sections"] if s["key"] == "income"
                for li in s["line_items"] if li["label"] == "Take Home Salary (Zus)"
            )
            assert any(t["transaction_id"] == txn_id for t in restored_zus["transactions"]), \
                "transaction should be restored to Take Home Salary (Zus)"
            print("Cleanup OK: transaction restored to its original category.")

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("ALL THREE FEATURES VERIFIED OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
