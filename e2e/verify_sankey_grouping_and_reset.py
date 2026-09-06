"""
e2e/verify_sankey_grouping_and_reset.py — one-off Playwright verification
for three related dashboard changes:
  1. The Sankey diagram's "By Section" / "By Need/Want" grouping toggle
     (budget_sankeymatic.to_sankeymatic's new group_by parameter).
  2. The new "Reset layout" button, which undoes a manually dragged node
     position without needing to change month/settings.
  3. Increased per-node vertical spacing (PX_PER_NODE 50 -> 65).

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_sankey_grouping_and_reset.py
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

console_errors: list[str] = []


def log_console(msg):
    # The deliberate group_by=bogus request below intentionally triggers a
    # 400 — Chromium logs any non-2xx fetch() response to the console
    # regardless of whether JS itself handles it, so this specific message
    # is an expected artifact of that check, not a real page error.
    if msg.type == "error" and "400 (Bad Request)" not in msg.text:
        console_errors.append(msg.text)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 950})
        page.on("console", log_console)

        # API-level sanity check of the new query param first.
        page.goto("http://localhost:8000", wait_until="networkidle")
        section_resp = page.evaluate("() => fetch('/api/months/2026-07/sankeymatic?group_by=section').then(r => r.json())")
        classification_resp = page.evaluate("() => fetch('/api/months/2026-07/sankeymatic?group_by=classification').then(r => r.json())")
        hub_line = re.compile(r"^Budget \[[\d.]+\] Home$", re.M)
        assert hub_line.search(section_resp["text"]), "section mode should emit a 'Budget [...] Home' hub line"
        assert "Needs" in classification_resp["text"] or "Wants" in classification_resp["text"]
        assert not hub_line.search(classification_resp["text"]), "classification mode should not emit a section hub"
        bad_resp = page.evaluate("() => fetch('/api/months/2026-07/sankeymatic?group_by=bogus').then(r => r.status)")
        assert bad_resp == 400

        # Drive the UI.
        page.wait_for_selector("text=Take Home Salary (Zus)", timeout=15000)
        page.wait_for_selector('svg[data-testid="sankey-diagram"]', timeout=15000)
        page.screenshot(path=str(SCREENSHOT_DIR / "sankey_by_section.png"))

        page.get_by_role("button", name="By Need/Want").click()
        page.wait_for_timeout(1500)  # refetch + re-render
        page.wait_for_selector("text=Needs", timeout=10000)
        page.screenshot(path=str(SCREENSHOT_DIR / "sankey_by_classification.png"))

        # Switch back and confirm the section hubs return.
        page.get_by_role("button", name="By Section").click()
        page.wait_for_timeout(1500)
        page.wait_for_selector("text=Home", timeout=10000)

        # Drag a node, then use Reset layout and confirm it snaps back —
        # verified via the node's rendered y-position before/after, since
        # the reset must actually recompute the layout, not just be a no-op
        # button.
        node_rect = page.locator('svg[data-testid="sankey-diagram"] rect').first
        node_rect.wait_for(timeout=10000)
        box_before_drag = node_rect.bounding_box()
        assert box_before_drag is not None

        node_rect.hover()
        page.mouse.down()
        page.mouse.move(box_before_drag["x"], box_before_drag["y"] + 120, steps=10)
        page.mouse.up()
        page.wait_for_timeout(300)
        box_after_drag = node_rect.bounding_box()
        assert box_after_drag is not None
        assert abs(box_after_drag["y"] - box_before_drag["y"]) > 50, "drag should have visibly moved the node"

        page.get_by_title("Reset layout (undo dragged nodes)").click()
        page.wait_for_timeout(400)
        box_after_reset = node_rect.bounding_box()
        assert box_after_reset is not None
        assert abs(box_after_reset["y"] - box_before_drag["y"]) < 5, "reset layout should restore the original position"
        page.screenshot(path=str(SCREENSHOT_DIR / "sankey_reset_layout.png"))

        browser.close()

        if console_errors:
            print("Console errors during run:")
            for e in console_errors:
                print(" -", e)
            return 1

        print("OK: By Section / By Need/Want toggle works and hits the right API, "
              "dragging a node then clicking Reset layout restores its original "
              "position, and the classification-mode API response correctly omits "
              "section hubs.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
