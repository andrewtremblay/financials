"""
plaid_link.py — Link a new bank/credit-card account via Plaid Link.

Usage:
    uv run plaid_link.py

Opens a browser to a local page that hosts Plaid's Link UI. Pick any
institution (Schwab, Bank of America, Barclays, PayPal, etc.) and log in.
On success the resulting item (access token + linked accounts) is appended
to plaid_items.json. Run this once per account you want to connect.
"""

import json
import http.server
import os
import threading
import webbrowser

from dotenv import load_dotenv

from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest

# Plaid defaults to 90 days of transaction history per Item, and this value
# is fixed for the life of the Item once set — request the 24-month max
# up front so we don't have to relink later to backfill more history.
TRANSACTIONS_DAYS_REQUESTED = 730

from plaid_client import get_plaid_client, load_items, save_items

load_dotenv()

PORT = 8090
CLIENT_USER_ID = "local-hobby-user"

_LINK_PAGE = """\
<!doctype html>
<html>
<head><title>Link a Plaid account</title></head>
<body style="font-family: sans-serif; max-width: 640px; margin: 40px auto;">
  <h2>Link a bank or credit card account</h2>
  <p id="status">Preparing Plaid Link...</p>
  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <script>
    fetch('/create_link_token', {method: 'POST'})
      .then(r => r.json())
      .then(data => {
        document.getElementById('status').innerText = 'Ready. Opening Plaid Link...';
        const handler = Plaid.create({
          token: data.link_token,
          onSuccess: (public_token, metadata) => {
            document.getElementById('status').innerText = 'Linked! Finishing up...';
            fetch('/exchange_public_token', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                public_token: public_token,
                institution_name: (metadata.institution && metadata.institution.name) || 'Unknown',
              }),
            }).then(() => {
              document.getElementById('status').innerText =
                'Account linked! You can close this tab.';
            });
          },
          onExit: (err, metadata) => {
            document.getElementById('status').innerText =
              err ? ('Link exited with an error: ' + JSON.stringify(err)) : 'Link exited. You can close this tab.';
          },
        });
        handler.open();
      })
      .catch(err => {
        document.getElementById('status').innerText = 'Error creating link token: ' + err;
      });
  </script>
</body>
</html>
"""


def create_link_token(client) -> str:
    request = LinkTokenCreateRequest(
        client_name="Financials (local)",
        language="en",
        country_codes=[CountryCode("US")],
        user=LinkTokenCreateRequestUser(client_user_id=CLIENT_USER_ID),
        products=[Products("transactions")],
        transactions=LinkTokenTransactions(days_requested=TRANSACTIONS_DAYS_REQUESTED),
    )
    redirect_uri = os.getenv("PLAID_REDIRECT_URI")
    if redirect_uri:
        request.redirect_uri = redirect_uri
    response = client.link_token_create(request)
    return response.link_token


def exchange_public_token(client, public_token: str, institution_name: str) -> dict:
    exchange_response = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token = exchange_response.access_token
    item_id = exchange_response.item_id

    accounts_response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    accounts = [
        {
            "account_id": account.account_id,
            "name": account.name,
            "mask": account.mask,
            "subtype": str(account.subtype) if account.subtype else None,
        }
        for account in accounts_response.accounts
    ]

    items = load_items()
    items[item_id] = {
        "item_id": item_id,
        "access_token": access_token,
        "institution_name": institution_name,
        "accounts": accounts,
        "cursor": None,
    }
    save_items(items)
    return items[item_id]


def make_handler(client, done_event: threading.Event):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep terminal output quiet

        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            body = _LINK_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length else b""

            if self.path == "/create_link_token":
                link_token = create_link_token(client)
                self._send_json({"link_token": link_token})
                return

            if self.path == "/exchange_public_token":
                payload = json.loads(raw_body or b"{}")
                item = exchange_public_token(
                    client,
                    payload["public_token"],
                    payload.get("institution_name", "Unknown"),
                )
                print(f"\nLinked {item['institution_name']} — accounts:")
                for account in item["accounts"]:
                    print(f"  {account['name']} (...{account['mask']}) [{account['subtype']}]")
                self._send_json({"ok": True})
                done_event.set()
                return

            self.send_response(404)
            self.end_headers()

        def _send_json(self, data: dict):
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    client = get_plaid_client()
    done_event = threading.Event()
    handler = make_handler(client, done_event)

    with http.server.ThreadingHTTPServer(("", PORT), handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"Serving Plaid Link at {url}")
        print("Complete the flow in your browser. Press Ctrl+C to cancel.\n")
        threading.Timer(0.5, webbrowser.open, args=[url]).start()

        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        try:
            done_event.wait()
        except KeyboardInterrupt:
            print("\nCancelled.")
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    main()
