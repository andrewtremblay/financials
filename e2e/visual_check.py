"""
e2e/visual_check.py — Playwright visual/functional check for the budget
dashboard, run against a locally-running production server
(http://localhost:8000 by default — see README.md's "production
single-process" instructions).

This is the persistent home for browser verification: screenshots land in
e2e/screenshots/ (gitignored — they're baseline artifacts for comparing
before/after a change, not something to commit) and get overwritten on each
run, so the latest run is always the current state of the app. Compare
against a previous run's screenshots (copy them aside first, or just
remember what you saw) when evaluating whether a fix actually worked —
don't trust "no console errors" alone for anything visual.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/visual_check.py
    uv run python3 e2e/visual_check.py --base-url http://localhost:8000
"""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url

    SCREENSHOT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", log_console)
        page.on("pageerror", log_page_error)

        print("=== Loading dashboard ===")
        page.goto(base, wait_until="networkidle")
        page.wait_for_selector("text=Budget Dashboard", timeout=10000)
        page.wait_for_timeout(500)  # let the debounced Sankey parse/render settle
        page.screenshot(path=str(SCREENSHOT_DIR / "01_dashboard.png"))

        month_select = page.locator("select").first
        selected_value = month_select.input_value()
        print("Selected month:", selected_value)

        # Not "svg" alone / .first — the theme toggle's icon is also an
        # <svg> and sits earlier in the DOM (nav bar) than the diagram, so
        # .first started grabbing a 15x15 icon instead once dark mode
        # landed (2026-08-01). data-testid is a stable, purpose-built hook.
        svg = page.locator('svg[data-testid="sankey-diagram"]').first
        print("Sankey SVG size:", svg.get_attribute("width"), "x", svg.get_attribute("height"))
        # The dashboard's diagram panel scrolls (rather than shrinking to
        # fit), and several ancestors up the layout (App.tsx's own
        # `overflow-hidden` shell) also clip anything past their own box. An
        # element screenshot paints only what's actually visible on screen,
        # so a tall SVG comes back blank past whichever ancestor clips first.
        # Walk every ancestor and lift overflow clipping for the capture,
        # then restore exactly what was touched.
        svg.evaluate("""
            el => {
                let node = el.parentElement;
                while (node) {
                    if (node.style.overflow !== 'visible') {
                        node.setAttribute('data-e2e-prev-overflow', node.style.overflow);
                        node.style.overflow = 'visible';
                    }
                    node = node.parentElement;
                }
            }
        """)
        svg.screenshot(path=str(SCREENSHOT_DIR / "02_sankey_full.png"))
        page.evaluate("""
            () => {
                document.querySelectorAll('[data-e2e-prev-overflow]').forEach(node => {
                    node.style.overflow = node.getAttribute('data-e2e-prev-overflow');
                    node.removeAttribute('data-e2e-prev-overflow');
                });
            }
        """)

        print("\n=== Collapsing/expanding a section ===")
        # Structural selector (direct-child button of a section's bordered
        # wrapper) rather than a specific border color class — the color
        # class now varies by theme (border-gray-200 light / dark:border-
        # gray-800 dark), so matching on it broke this selector (2026-08-01).
        home_section_button = page.locator("div.border-b > button", has_text="Home").first
        home_section_button.click()
        page.wait_for_timeout(200)
        page.screenshot(path=str(SCREENSHOT_DIR / "03_home_collapsed.png"))
        home_section_button.click()
        page.wait_for_timeout(200)

        print("\n=== Opening a line item's notes drawer ===")
        line_item_row = page.get_by_role("button", name="Mortgage (12 Warren)")
        line_item_row.click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(SCREENSHOT_DIR / "04_notes_drawer.png"))
        page.locator("div.absolute.inset-0.bg-black\\/40").first.click()
        page.wait_for_timeout(200)

        print("\n=== Needs Review queue ===")
        needs_review_badge = page.locator("text=/^⚠/").first
        if needs_review_badge.count() > 0:
            print("Needs-review badge text:", needs_review_badge.text_content())
            needs_review_badge.click()
            page.wait_for_timeout(300)
            page.screenshot(path=str(SCREENSHOT_DIR / "05_needs_review_drawer.png"))
            # NotesDrawer has no Escape-key handler — only closes via
            # backdrop click (same as the line-item drawer above). This
            # step silently never ran before (no test month ever had a
            # needs-review item until now), leaving the drawer open and
            # blocking every click for the rest of the script (2026-08-01).
            page.locator("div.absolute.inset-0.bg-black\\/40").first.click()
        else:
            print("No needs-review badge (0 items needing review).")

        print("\n=== Switching months ===")
        all_values = month_select.locator("option").evaluate_all("els => els.map(e => e.value)")
        other = next(v for v in all_values if v != selected_value)
        month_select.select_option(other)
        page.wait_for_timeout(1500)
        print("Switched to:", month_select.input_value())
        page.screenshot(path=str(SCREENSHOT_DIR / "06_month_switched.png"))
        month_select.select_option(selected_value)  # back to original for a stable baseline
        page.wait_for_timeout(1500)

        print("\n=== Sankey Builder tab ===")
        page.locator("button", has_text="Sankey Builder").click()
        page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOT_DIR / "07_sankey_builder_tab.png"))

        browser.close()

    print(f"\nScreenshots written to {SCREENSHOT_DIR}")
    print("\n=== Console errors ===")
    for e in console_errors:
        print("  ", e)
    print("=== Page errors (uncaught exceptions) ===")
    for e in page_errors:
        print("  ", e)

    if console_errors or page_errors:
        print("\nFAIL: console/page errors present")
        sys.exit(1)
    print("\nALL CHECKS PASSED, NO CONSOLE/PAGE ERRORS")


if __name__ == "__main__":
    main()
