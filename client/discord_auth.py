"""
Handles the client's half of Discord OAuth: open the system browser to
Discord's login/consent page, then catch the redirect on a temporary local
web server (Discord sends the browser back to http://localhost:PORT/callback
with a "code" in the URL, which we grab).

The resulting code is sent to OUR server's /discord/callback, which holds
the client secret and bot token and does the actual identity + role check -
neither of those secrets ever need to live in this distributed client app.
"""

import http.server
import socketserver
import threading
import urllib.parse
import webbrowser

REDIRECT_PORT = 5900
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

SUCCESS_HTML = b"<html><body><h2>Login successful. You can close this tab and return to the app.</h2></body></html>"
FAILURE_HTML = b"<html><body><h2>Login failed or was cancelled. You can close this tab.</h2></body></html>"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get("code", [None])[0]
        self.server.received_code = code

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(SUCCESS_HTML if code else FAILURE_HTML)

    def log_message(self, format, *args):
        pass  # silence default request logging to stdout


def login_with_discord(client_id: str, timeout: int = 120):
    """
    Opens the system browser for Discord OAuth and waits (up to `timeout`
    seconds) for the redirect. Returns the authorization code, or None if
    it timed out or the user cancelled.
    """
    server = socketserver.TCPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.received_code = None
    server.timeout = timeout

    thread = threading.Thread(target=server.handle_request)
    thread.start()

    auth_url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=identify"
    )
    webbrowser.open(auth_url)

    thread.join(timeout=timeout)
    server.server_close()

    return server.received_code
