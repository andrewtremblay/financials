"""Unit tests for the pure diagram-sizing / deep-link helpers in serve_frontend.py.

These functions only depend on the standard library plus ``lzstring`` — no heavy
ML dependencies — so they make a good, fast baseline.
"""
import lzstring

from serve_frontend import compute_diagram_size, diagram_to_url


class TestComputeDiagramSize:
    def test_empty_diagram_returns_default_size(self):
        assert compute_diagram_size("") == (1200, 800)

    def test_whitespace_only_returns_default_size(self):
        assert compute_diagram_size("\n   \n") == (1200, 800)

    def test_simple_two_node_flow_is_deterministic(self):
        # One flow, two nodes, two columns -> smallest allowed width, min height.
        assert compute_diagram_size("A [10] B") == (400, 600)

    def test_more_columns_widen_the_diagram(self):
        two_col = compute_diagram_size("A [10] B")[0]
        three_col = compute_diagram_size("A [10] B\nB [10] C")[0]
        assert three_col > two_col

    def test_height_is_capped(self):
        # A hugely lopsided flow would blow past the cap without clamping.
        diagram = "Budget [100000] Rent\nBudget [1] Gum"
        _, height = compute_diagram_size(diagram)
        assert height <= 2000

    def test_dimensions_are_ints(self):
        w, h = compute_diagram_size("Wages [3000] Budget\nBudget [1000] Food")
        assert isinstance(w, int) and isinstance(h, int)


class TestDiagramToUrl:
    def test_url_prefix_and_port(self):
        url = diagram_to_url("A [10] B")
        assert url.startswith("http://localhost:8080/?i=")

    def test_custom_port(self):
        url = diagram_to_url("A [10] B", port=9999)
        assert url.startswith("http://localhost:9999/?i=")

    def test_payload_round_trips_and_embeds_size(self):
        diagram = "Wages [3000] Budget\nBudget [1000] Food"
        url = diagram_to_url(diagram, width=800, height=600)
        compressed = url.split("?i=", 1)[1]
        decoded = lzstring.LZString().decompressFromEncodedURIComponent(compressed)
        assert diagram in decoded
        assert "size w 800" in decoded
        assert "size h 600" in decoded
