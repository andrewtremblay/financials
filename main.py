import argparse
import http.server
import socketserver
import threading
import webbrowser
from analyze_pdf import main
from serve_frontend import diagram_to_url, Handler, PORT

MONTH_NAMES = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0

def open_in_browser(diagram: str):
    url = diagram_to_url(diagram)
    if is_port_in_use(PORT):
        print(f"Server already running — opening {url}")
        webbrowser.open(url)
        return
    try:
        httpd = socketserver.TCPServer(("", PORT), Handler)
    except OSError:
        print(f"Server already running — opening {url}")
        webbrowser.open(url)
        return
    with httpd:
        print(f"Serving frontend at {url}")
        threading.Timer(0.5, webbrowser.open, args=[url]).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

def handle():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", type=str, default=None, help="Filter by month abbreviation (e.g. jan, feb, mar)", choices=MONTH_NAMES.keys())
    parser.add_argument("--open", action="store_true", help="Open the Sankeymatic diagram in a browser after analysis")
    parser.add_argument("--inbox-only", action="store_true", help="Process only data/inbox/ — skip bank-specific subfolders (only applies to --source pdf/all)")
    parser.add_argument(
        "--source", choices=["plaid", "pdf", "all"], default="plaid",
        help="Data source: 'plaid' (default) syncs+reads data/plaid/ only, 'pdf' parses statements only, 'all' does both (no dedup between them yet)",
    )
    parser.add_argument(
        "--plaid-max-age-hours", type=float, default=24.0,
        help="Skip re-syncing a Plaid item if it was synced within this many hours (default: 24)",
    )
    args = parser.parse_args()
    month = args.month
    if month is not None:
        key = month.lower()[:3]
        if key not in MONTH_NAMES:
            raise ValueError(f"Unknown month: {month!r}. Use a 3-letter abbreviation like 'jan', 'feb', etc.")
    diagram = main(
        month,
        inbox_only=args.inbox_only,
        source=args.source,
        plaid_max_age_hours=args.plaid_max_age_hours,
    )
    if args.open and diagram:
        open_in_browser(diagram)

if __name__ == "__main__":
    print('Starting analysis')
    handle()
