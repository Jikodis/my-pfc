#!/usr/bin/env python3
"""
TRMNL polling endpoint — serve plugin payloads over HTTP, built per request.

    python3 automations/scripts/trmnl_serve.py [--port 8765] [--host 127.0.0.1]

Routes:
    GET /healthz        no auth; liveness only, returns "ok"
    GET /p/<plugin>     bearer-authenticated; the plugin's payload as JSON

Payloads are built **per request** from current repo state — that is the whole
point of the polling transport. TRMNL refreshes a plugin's data right before
showing its screen, so a request-time build means the wall is current as of the
moment you look at it.

Binds to loopback by default. Put a TLS-terminating reverse proxy (Caddy) in
front of it; do not expose this process directly. Auth is a bearer token in
$TRMNL_SERVE_TOKEN, which TRMNL sends via the plugin's polling headers. The
server refuses to start without one.

Setup: docs/install/trmnl-endpoint.md
"""

import argparse
import hmac
import json
import secrets
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from trmnl_push import BUILDERS, load_env, today_local  # noqa: E402

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"


class PayloadHandler(BaseHTTPRequestHandler):
    server_version = "pfc-trmnl/1.0"

    # Set by main() before the server starts.
    token = ""
    env = {}

    def _send(self, status, body, content_type="application/json"):
        payload = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status, message):
        self._send(status, json.dumps({"error": message}))

    def _authorized(self):
        """Constant-time bearer check, so a wrong token leaks no timing signal."""
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        return hmac.compare_digest(header[len(prefix):].strip(), self.token)

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")

        if path == "/healthz":
            self._send(200, "ok", content_type="text/plain")
            return

        if not path.startswith("/p/"):
            self._error(404, "not found")
            return

        # Auth before existence: an unauthenticated caller learns nothing about
        # which plugins exist.
        if not self._authorized():
            self._error(401, "unauthorized")
            return

        plugin = path[len("/p/"):]
        builder = BUILDERS.get(plugin)
        if builder is None:
            self._error(404, f"no builder for '{plugin}'")
            return

        try:
            payload = builder(self.env, today_local(self.env))
        except Exception:
            # Log the trace for the operator; return nothing useful to the caller.
            traceback.print_exc(file=sys.stderr)
            self._error(500, "payload build failed")
            return

        self._send(200, json.dumps(payload))

    def log_message(self, fmt, *args):
        # The default handler logging adds a timestamp systemd already supplies.
        # Keep it terse for the journal.
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


def main(argv):
    parser = argparse.ArgumentParser(description="Serve TRMNL plugin payloads.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=None, help=f"bind port (default {DEFAULT_PORT} or $TRMNL_SERVE_PORT)")
    parser.add_argument("--gen-token", action="store_true", help="print a fresh random token and exit")
    args = parser.parse_args(argv)

    if args.gen_token:
        print(secrets.token_urlsafe(32))
        return 0

    env = load_env()
    token = env.get("TRMNL_SERVE_TOKEN", "")
    if not token:
        print(
            "TRMNL_SERVE_TOKEN is not set. Generate one with:\n"
            "    python3 automations/scripts/trmnl_serve.py --gen-token\n"
            "then put it in .env as TRMNL_SERVE_TOKEN=<value> and use the same value "
            "in the plugin's polling headers. Refusing to serve unauthenticated.",
            file=sys.stderr,
        )
        return 1

    port = args.port or int(env.get("TRMNL_SERVE_PORT", DEFAULT_PORT))

    PayloadHandler.token = token
    PayloadHandler.env = env

    server = ThreadingHTTPServer((args.host, port), PayloadHandler)
    print(
        f"serving {len(BUILDERS)} plugin(s) on http://{args.host}:{port} "
        f"({', '.join(sorted(BUILDERS))})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
