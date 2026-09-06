"""
e2e/verify_ignored_transactions.py — one-off Playwright verification for the
"Ignore this transaction" feature: RecategorizeModal's new ignore mode (with
a note field), the sidebar's new Ignored section at the bottom of the list
(with an editable note), and confirming ignored transactions are excluded
from every total and the Sankey diagram.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_ignored_transactions.py
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

        # Baseline totals before ignoring anything.
        before = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
        income_before = before["totals"]["income"]
        assert before["ignored"] == [], "expected no ignored transactions before this run"

        # Grab a real transaction_id + amount from a non-income line item so
        # we can confirm it disappears from that line item's total.
        daily_living = next(s for s in before["sections"] if s["key"] == "DAILY LIVING")
        groceries = next(li for li in daily_living["line_items"] if li["label"] == "Groceries")
        assert groceries["transactions"], "need at least one real Groceries transaction to ignore"
        target = groceries["transactions"][0]
        target_amount = target["amount"]
        groceries_before = groceries["actual"]

        # Open Recategorize on that transaction via the drawer.
        page.click("text=Groceries")
        page.wait_for_selector('button[title="Recategorize"]', timeout=10000)
        page.click('button[title="Recategorize"]')
        modal = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal.wait_for(timeout=10000)

        modal.get_by_role("button", name="Ignore this transaction instead").click()
        note_input = modal.locator("textarea")
        note_input.wait_for(timeout=5000)
        note_input.fill("Playwright verification: not a real expense")
        page.screenshot(path=str(SCREENSHOT_DIR / "ignore_transaction_form.png"))
        modal.get_by_role("button", name="Save").click()
        modal.wait_for(state="detached", timeout=15000)

        # Sidebar should now show an Ignored section with our note, and the
        # Groceries total should have dropped by exactly the ignored amount.
        after = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
        assert len(after["ignored"]) == 1, f"expected exactly 1 ignored transaction, got {after['ignored']}"
        ignored_entry = after["ignored"][0]
        assert ignored_entry["note"] == "Playwright verification: not a real expense"
        assert abs(ignored_entry["amount"] - target_amount) < 0.01

        daily_living_after = next(s for s in after["sections"] if s["key"] == "DAILY LIVING")
        groceries_after = next(li for li in daily_living_after["line_items"] if li["label"] == "Groceries")
        assert abs((groceries_before - groceries_after["actual"]) - target_amount) < 0.01, \
            "Groceries total should have dropped by exactly the ignored transaction's amount"
        assert abs(after["totals"]["income"] - income_before) < 0.01, "ignoring an expense must not touch income"

        # The Sankey diagram text must not mention the ignored transaction's
        # description anywhere (it's excluded from the flows entirely).
        sankey = page.evaluate("() => fetch('/api/months/2026-07/sankeymatic').then(r => r.json())")
        assert target["description"] not in sankey["text"]

        # The sidebar's Ignored section should be visible with the note.
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=/Ignored \\(1\\)/", timeout=10000)
        note_field = page.locator('input[placeholder="Why was this ignored?"]')
        note_field.wait_for(timeout=5000)
        assert note_field.input_value() == "Playwright verification: not a real expense"
        page.screenshot(path=str(SCREENSHOT_DIR / "ignored_section_sidebar.png"))

        # Edit the note inline (no recategorize) and confirm it persists
        # without triggering a slow resync (should be near-instant).
        note_field.fill("Playwright verification: edited note")
        note_field.blur()
        page.wait_for_timeout(500)
        edited = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
        assert edited["ignored"][0]["note"] == "Playwright verification: edited note"

        # Un-ignore via the pencil icon -> pick a real category again.
        page.hover('input[placeholder="Why was this ignored?"]')
        edit_button = page.locator('button[title="Recategorize (un-ignore)"]')
        edit_button.click()
        modal2 = page.get_by_role("dialog").filter(has_text="Recategorize")
        modal2.wait_for(timeout=10000)
        # Should reopen already in ignore mode (transaction.category is IGNORED).
        modal2.get_by_role("button", name="← Pick a category instead").click()
        modal2.locator("select").first.select_option(label=next(
            o for o in modal2.locator("select").first.locator("option").all_inner_texts() if "GROCERIES" in o
        ))
        modal2.get_by_role("button", name="Save").click()
        modal2.wait_for(state="detached", timeout=15000)

        restored = page.evaluate("() => fetch('/api/months/2026-07').then(r => r.json())")
        assert restored["ignored"] == [], f"expected transaction to be un-ignored, got {restored['ignored']}"

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: ignore/note-edit/un-ignore flow works, ignored transactions excluded "
              "from totals and the Sankey diagram, and shown with their note in the "
              "sidebar's Ignored section.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
