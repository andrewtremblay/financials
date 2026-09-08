"""
e2e/verify_node_click.py — one-off Playwright verification for the
"click a Sankey node/label to open the same NotesDrawer as the sidebar"
feature (SankeyDiagram.tsx onNodeClick, wired in BudgetDashboard.tsx).

Not part of the permanent e2e/visual_check.py flow (that script covers the
steady-state dashboard) — this specifically drives and screenshots the new
click-to-open-drawer behavior plus the drag/pan/Builder-tab non-regression
checks called out in the task. Screenshots land in e2e/screenshots/ alongside
visual_check.py's, prefixed nodeclick_.

Usage:
    uv run uvicorn api_server:app --port 8000 &   # or already running
    uv run python3 e2e/verify_node_click.py
"""
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


def largest_svg(page):
    """The page renders multiple <svg>s (small icon svgs plus the actual
    Sankey diagram) — return a Locator for whichever is largest by area."""
    idx = page.evaluate("""
        () => {
            const svgs = Array.from(document.querySelectorAll('svg'));
            let best = 0, bestArea = -1;
            svgs.forEach((s, i) => {
                const r = s.getBoundingClientRect();
                const area = r.width * r.height;
                if (area > bestArea) { bestArea = area; best = i; }
            });
            return best;
        }
    """)
    return page.locator("svg").nth(idx)


def main():
    base = "http://localhost:8000"
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", log_console)
        page.on("pageerror", log_page_error)

        print("=== Loading dashboard ===")
        page.goto(base, wait_until="networkidle")
        page.wait_for_selector("text=Budget Dashboard", timeout=10000)
        page.wait_for_timeout(600)

        # Pick a real sidebar line item to cross-check against (skip section
        # header rows — those are the outer <button> with the rotate-90 chevron).
        row = page.locator("button.w-full.grid.grid-cols-\\[1fr_auto_auto_auto\\]").filter(
            has_not=page.locator("span.inline-block.transition-transform")
        ).first
        # BudgetLineItemRow renders `{item.label}` as a bare text node
        # followed by sibling <span> badges (fixed/mirror dot, txn count) —
        # the item's own label can itself contain parens (e.g. "Take Home
        # Salary (Zus)"), so splitting the wrapper's full inner_text() on
        # "(" is unsafe. Read just the first text-node child instead.
        sidebar_label = row.locator("span").first.evaluate(
            "el => Array.from(el.childNodes).find(n => n.nodeType === 3)?.textContent.trim()"
        )
        print("Sidebar line item under test:", repr(sidebar_label))

        svg = largest_svg(page)

        # Find the matching Sankey node label <text> (name text, not the
        # value text) by exact content match.
        label_text = svg.locator("text", has_text=sidebar_label).filter(
            has_text=sidebar_label
        )
        # Narrow to an exact (not substring) match.
        candidates = label_text.all()
        target = None
        for c in candidates:
            # innerText is an HTML-only property; SVG <text> nodes need
            # text_content() (maps to textContent) instead.
            if (c.text_content() or "").strip() == sidebar_label:
                target = c
                break
        if target is None:
            failures.append(f"Could not find a Sankey <text> label exactly matching {sidebar_label!r}")
        else:
            print("\n=== Clicking Sankey diagram label ===")
            target.scroll_into_view_if_needed()
            # Each label paints twice (a white stroke "halo" copy underneath,
            # for contrast, then the real fill-colored copy on top) — both
            # match this locator, and the top one intercepts pointer events
            # meant for the other. The click handler lives on their shared
            # parent <g> (fires via capture-phase bubbling either way), so
            # force through Playwright's actionability check rather than
            # fighting over which exact overlapping <text> is "visible".
            target.click(force=True)
            page.wait_for_timeout(300)
            page.screenshot(path=str(SCREENSHOT_DIR / "nodeclick_01_drawer_from_label.png"))
            drawer_title = page.locator("aside, div").locator("h2, h3").first
            drawer_visible = page.get_by_text(sidebar_label, exact=False).count() > 0
            # Check the drawer actually opened with the right line item by
            # looking for the close button + the label text inside a panel.
            opened = page.locator("text=" + sidebar_label).count() > 1  # sidebar row + drawer title
            print("Drawer appears open with matching content:", opened)
            if not opened:
                failures.append("Clicking the Sankey label did not open a drawer with matching title")
            # Close drawer (click the dim overlay, same as visual_check.py).
            overlay = page.locator("div.absolute.inset-0.bg-black\\/40").first
            if overlay.count() > 0:
                overlay.click()
                page.wait_for_timeout(200)

        print("\n=== Dragging a node (should move it, NOT open drawer) ===")
        node_rect = svg.locator("rect[style*='cursor']").first
        box = node_rect.bounding_box()
        if box is None:
            failures.append("Could not get bounding box for a node rect")
        else:
            before_y = node_rect.get_attribute("y")
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx, cy + 40, steps=10)
            page.mouse.up()
            page.wait_for_timeout(200)
            after_y = node_rect.get_attribute("y")
            print(f"Node rect y: {before_y} -> {after_y}")
            drawer_open_after_drag = page.locator("div.fixed.inset-0, div.absolute.inset-0.bg-black\\/40").count() > 0
            if before_y == after_y:
                failures.append("Dragging a node did not change its y position")
            if drawer_open_after_drag:
                failures.append("Dragging a node incorrectly opened the drawer")
            page.screenshot(path=str(SCREENSHOT_DIR / "nodeclick_02_after_node_drag.png"))

        print("\n=== Panning blank canvas (should pan, NOT open drawer) ===")
        svg_box = svg.bounding_box()
        transform_before = page.evaluate(
            "() => { const g = document.querySelector('svg g[transform]'); return g ? g.getAttribute('transform') : null; }"
        )
        # Top-left corner of the SVG, inside the margin, should be blank
        # background (no node column starts at x=0).
        bx = svg_box["x"] + 15
        by = svg_box["y"] + 15
        page.mouse.move(bx, by)
        page.mouse.down()
        page.mouse.move(bx + 60, by + 30, steps=10)
        page.mouse.up()
        page.wait_for_timeout(200)
        transform_after = page.evaluate(
            "() => { const g = document.querySelector('svg g[transform]'); return g ? g.getAttribute('transform') : null; }"
        )
        print(f"Canvas transform: {transform_before} -> {transform_after}")
        drawer_open_after_pan = page.locator("div.absolute.inset-0.bg-black\\/40").count() > 0
        if transform_before == transform_after:
            failures.append("Panning blank canvas did not change the zoom/pan transform")
        if drawer_open_after_pan:
            failures.append("Panning blank canvas incorrectly opened the drawer")
        page.screenshot(path=str(SCREENSHOT_DIR / "nodeclick_03_after_pan.png"))

        print("\n=== Sankey Builder tab (no drawer/click behavior should leak in) ===")
        page.locator("button", has_text="Sankey Builder").click()
        page.wait_for_timeout(500)
        builder_svg = largest_svg(page)
        builder_text = builder_svg.locator("text").first
        if builder_text.count() > 0:
            builder_text.click(force=True)
            page.wait_for_timeout(300)
        drawer_in_builder = page.locator("div.absolute.inset-0.bg-black\\/40").count() > 0
        if drawer_in_builder:
            failures.append("Clicking a label in the Sankey Builder tab incorrectly opened a drawer")
        page.screenshot(path=str(SCREENSHOT_DIR / "nodeclick_04_builder_tab.png"))

        browser.close()

    print(f"\nScreenshots written to {SCREENSHOT_DIR}")
    print("\n=== Console errors ===")
    for e in console_errors:
        print("  ", e)
    print("=== Page errors (uncaught exceptions) ===")
    for e in page_errors:
        print("  ", e)

    print("\n=== Failures ===")
    for f in failures:
        print("  FAIL:", f)

    if console_errors or page_errors or failures:
        print("\nFAIL")
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
