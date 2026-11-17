#!/usr/bin/env python3
"""
TRMNL polling endpoint — serve plugin payloads over HTTP, built per request.

    python3 automations/scripts/trmnl_serve.py [--port 8765] [--host 127.0.0.1]

Routes:
    GET /healthz        no auth; liveness only, returns "ok"
    GET /p/<plugin>     bearer-authenticated; the plugin's payload as JSON
    GET /p/pod/<secret>/<file>   the AI News podcast feed and its MP3s (docs/ai-news.md);
                        the secret in the path is the guard, as a podcast app cannot
                        send a bearer header. GET and HEAD, with byte ranges.

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

# AI News podcast feed (ai_news.py): static files under data/.ai-news/feed/, served at
# /p/pod/<AI_NEWS_FEED_SECRET>/<file>. The reverse proxy already forwards /p/* here.
POD_ROOT = SCRIPT_DIR.parent.parent / "data" / ".ai-news" / "feed"
POD_TYPES = {".mp3": "audio/mpeg", ".xml": "application/rss+xml; charset=utf-8", ".jpg": "image/jpeg",
             ".png": "image/png"}


def resolve_pod_path(path, secret, root=POD_ROOT):
    """Map /p/pod/<secret>/<file> to a file under root, or None (wrong secret, traversal, missing)."""
    prefix = "/p/pod/"
    if not secret or not path.startswith(prefix):
        return None
    given, _, rest = path[len(prefix):].partition("/")
    if not hmac.compare_digest(given, secret) or not rest:
        return None
    root = Path(root).resolve()
    target = (root / rest).resolve()
    if root not in target.parents or not target.is_file() or target.suffix not in POD_TYPES:
        return None
    return target


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

    def _serve_pod(self, path, head=False):
        target = resolve_pod_path(path, self.env.get("AI_NEWS_FEED_SECRET", ""))
        if target is None:
            self._error(404, "not found")
            return
        size = target.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            try:
                start = int(a) if a else max(0, size - int(b))
                end = min(int(b), size - 1) if a and b else end
            except ValueError:
                start, end = 0, size - 1
        partial = bool(rng) and start <= end
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", POD_TYPES[target.suffix])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        with open(target, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                buf = f.read(min(65536, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def do_HEAD(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/p/pod/"):
            self._serve_pod(path, head=True)
        else:
            self._error(404, "not found")

    def do_GET(self):
        if self.path.split("?", 1)[0].startswith("/p/pod/"):
            self._serve_pod(self.path.split("?", 1)[0])
            return
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
