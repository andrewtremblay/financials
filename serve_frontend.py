#!/usr/bin/env python3
"""Serve the frontend/build directory on localhost."""

import http.server
import os
import re
import socketserver
from collections import defaultdict

import lzstring

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(__file__), "frontend_react", "dist")

EXAMPLE_DIAGRAM = """\
Wages [3000] Budget
Other Income [500] Budget

Budget [1200] Housing
Budget [600] Food
Budget [300] Fun
Budget [250] Transport
Budget [150] Subscriptions
Budget [1000] Savings
"""

# Pixels between adjacent nodes in the same column.
_MIN_GAP = 8
# Smallest acceptable node height in pixels (drives proportional scaling).
_MIN_NODE_PX = 10
# Hard cap on diagram height so it stays scrollable.
_MAX_HEIGHT = 2000
# Horizontal spacing between columns (node center to node center).
_COL_SPACING = 200
# Margins match DEFAULT_SETTINGS in the frontend.
_MARGIN_L, _MARGIN_R = 12, 12
_MARGIN_T, _MARGIN_B = 18, 20
_NODE_W = 9
_EXTRA = 50  # breathing room added to both dimensions



def compute_diagram_size(diagram: str) -> tuple[int, int]:
    """
    Compute (width, height) to naturally fit the diagram:
      height = sum of all values in the tallest column
               + (n_nodes - 1) * gap + margins + extra
      width  = (num_columns - 1) * col_spacing + node_w + margins + extra
    """
    flow_re = re.compile(
        r"^([^/'\[\n][^\[\n]*?)\s+\[(\d+(?:\.\d+)?)\]\s+([^\n#]+)",
        re.MULTILINE,
    )

    incoming: dict[str, float] = {}
    outgoing: dict[str, float] = {}
    adj: dict[str, list[str]] = defaultdict(list)

    for m in flow_re.finditer(diagram):
        src = m.group(1).strip()
        amt = float(m.group(2))
        tgt = m.group(3).strip()
        outgoing[src] = outgoing.get(src, 0) + amt
        incoming[tgt] = incoming.get(tgt, 0) + amt
        adj[src].append(tgt)

    all_nodes = set(incoming) | set(outgoing)
    if not all_nodes:
        return 1200, 800

    # BFS to assign each node its deepest column (longest-path depth).
    origins = [n for n in all_nodes if n not in incoming]
    stages: dict[str, int] = {n: 0 for n in origins}
    queue = list(origins)
    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        for neighbor in adj.get(node, []):
            new_stage = stages[node] + 1
            if stages.get(neighbor, -1) < new_stage:
                stages[neighbor] = new_stage
                queue.append(neighbor)
    for n in all_nodes:
        if n not in stages:
            stages[n] = 0

    num_columns = max(stages.values()) + 1

    # Group nodes by column; each node's "value" is its max flow.
    by_column: dict[int, list[float]] = defaultdict(list)
    for node in all_nodes:
        col = stages[node]
        value = max(incoming.get(node, 0.0), outgoing.get(node, 0.0))
        by_column[col].append(value)

    # Height: proportional scaling so the smallest node is at least _MIN_NODE_PX px.
    # For each column: required_h = _MIN_NODE_PX * sum(vals) / min_val + (n-1)*gap
    # We take the max across all columns, capped at _MAX_HEIGHT.
    all_vals = [v for vals in by_column.values() for v in vals if v > 0]
    min_val = min(all_vals) if all_vals else 1.0
    max_col_needed = max(
        _MIN_NODE_PX * sum(vals) / min_val + max(0, len(vals) - 1) * _MIN_GAP
        for vals in by_column.values()
    )
    height = int(min(_MAX_HEIGHT, max(600, max_col_needed + _MARGIN_T + _MARGIN_B + _EXTRA)))

    # Width: fit all columns with even horizontal spacing + margins + extra.
    width = int((num_columns - 1) * _COL_SPACING + _NODE_W + _MARGIN_L + _MARGIN_R + _EXTRA)

    return max(400, width), max(300, height)


def diagram_to_url(
    diagram: str,
    port: int = PORT,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Return a deep-link URL for the given Sankeymatic diagram text."""
    if width is None or height is None:
        auto_w, auto_h = compute_diagram_size(diagram)
        width = width if width is not None else auto_w
        height = height if height is not None else auto_h
    full_input = f"{diagram}\nsize w {width}\nsize h {height}\n"
    compressed = lzstring.LZString().compressToEncodedURIComponent(full_input)
    return f"http://localhost:{port}/?i={compressed}"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


if __name__ == "__main__":
    example_url = diagram_to_url(EXAMPLE_DIAGRAM)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving frontend at http://localhost:{PORT}")
        print(f"Example diagram:   {example_url}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
