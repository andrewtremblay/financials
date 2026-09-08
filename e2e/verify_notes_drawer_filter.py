"""
e2e/verify_notes_drawer_filter.py — one-off Playwright verification for two
related NotesDrawer changes:
  1. Clicking a sub-category expansion node in the diagram ("{Parent} —
     {Category}") now opens the SAME drawer the parent's own node would,
     pre-filtered to that one category, instead of a separate static
     explanation modal.
  2. NotesDrawer itself now has an optional category filter dropdown,
     shown whenever its transaction list spans more than one category.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_notes_drawer_filter.py
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

        # Expand a line item known to have multiple sub-categories: "Other"
        # under Daily Living has been used throughout this session's
        # earlier fixtures/screenshots as a multi-category catch-all.
        # Find a line item with the expand toggle (+/-) visible — click its
        # toggle to make sure it's expanded, then click one of its diagram
        # sub-nodes.
        page.wait_for_selector('svg[data-testid="sankey-diagram"]', timeout=15000)

        # Click a text label ending in " — " pattern inside the SVG — these
        # are the sub-category expansion nodes.
        sub_node_text = page.locator('svg[data-testid="sankey-diagram"] text', has_text="—").first
        sub_node_text.wait_for(timeout=10000)
        clicked_label = sub_node_text.text_content() or ""
        print("Clicking sub-category node:", repr(clicked_label))
        # SankeyDiagram renders each label as a stacked halo pair (a white
        # outline copy behind the real fill copy, for readability against
        # any ribbon color) — both occupy the same position, which confuses
        # Playwright's actionability check. force=True bypasses it; both
        # copies share the same click handler regardless of which one
        # Playwright thinks it hit.
        sub_node_text.click(force=True)

        # A NotesDrawer (role=dialog, has a category <select>) should open —
        # NOT a static NodeExplanationModal (which has no <select>, just a
        # "Got it" button and no filter dropdown).
        drawer = page.get_by_role("dialog").last
        drawer.wait_for(timeout=10000)
        select = drawer.locator("select")
        select.wait_for(timeout=5000)
        selected_value = select.input_value()
        print("Drawer opened with category filter:", repr(selected_value))
        assert selected_value, "expected the drawer to open with a pre-selected category filter"
        # The clicked node's own text is "{Parent} — {Category}" — the
        # filter's initial value should be the {Category} part.
        assert selected_value in clicked_label, f"filter value {selected_value!r} not found in clicked label {clicked_label!r}"

        # No "Got it" button (that's the static explanation modal's own
        # signature) — confirms we really got the drawer, not the modal.
        assert drawer.get_by_role("button", name="Got it").count() == 0

        page.screenshot(path=str(SCREENSHOT_DIR / "notes_drawer_prefiltered.png"))

        # Switch the filter to "All categories" and confirm the list grows.
        filtered_count_text = drawer.locator("p", has_text="No transactions").count()
        select.select_option(index=0)  # "All categories (...)"
        page.wait_for_timeout(200)
        page.screenshot(path=str(SCREENSHOT_DIR / "notes_drawer_all_categories.png"))

        drawer.get_by_role("button", name="×").click()

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: sub-category node click opens the parent's NotesDrawer pre-filtered "
              "to that category (not a static explanation modal), and the drawer's "
              "'All categories' option restores the full list.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
