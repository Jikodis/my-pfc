#!/usr/bin/env python3
"""
One-time Google Health OAuth2 setup.

BEFORE RUNNING:
  On your local machine, open an SSH tunnel so the browser redirect lands here:
    ssh -L 8080:localhost:8080 <your-vps-user>@<your-vps-ip>

Then run this script on the VPS:
    python3 automations/scripts/google_health_auth.py

Open the printed URL in your local browser. After approval, tokens are saved
to config/google_health_tokens.json (gitignored).
"""

import http.server
import json
import os
import threading
import urllib.parse
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]

def load_env():
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_env()

CLIENT_ID     = ENV.get("GOOGLE_HEALTH_CLIENT_ID")
CLIENT_SECRET = ENV.get("GOOGLE_HEALTH_CLIENT_SECRET")
TOKEN_FILE    = Path(ENV.get("GOOGLE_HEALTH_TOKEN_FILE", REPO_ROOT / "config/google_health_tokens.json"))
REDIRECT_URI  = "http://localhost:8080/callback"

# Scopes for sleep, resting heart rate, and active zone minutes
SCOPES = " ".join([
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
])

AUTH_URI  = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"

# ── OAuth flow ────────────────────────────────────────────────────────────────

auth_code = None
server_done = threading.Event()

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorization successful. You can close this tab.</h2>")
            print("\nAuthorization code received.")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"<h2>Error: {error}</h2>".encode())
            print(f"\nOAuth error: {error}")

        server_done.set()

    def log_message(self, *args):
        pass  # suppress default access logs


def build_auth_url():
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return AUTH_URI + "?" + urllib.parse.urlencode(params)


def exchange_code(code):
    data = urllib.parse.urlencode({
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }).encode()

    req = urllib.request.Request(TOKEN_URI, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def save_tokens(tokens):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    TOKEN_FILE.chmod(0o600)
    print(f"Tokens saved to {TOKEN_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: GOOGLE_HEALTH_CLIENT_ID / GOOGLE_HEALTH_CLIENT_SECRET not set in .env")
        return

    print("\n" + "="*60)
    print("Google Health OAuth2 Setup")
    print("="*60)
    print("\nSTEP 1 — On your LOCAL machine, open an SSH tunnel:")
    print(f"  ssh -L 8080:localhost:8080 <user>@<vps-ip>")
    print("\nSTEP 2 — Open this URL in your browser:")
    print(f"\n  {build_auth_url()}\n")
    print("Waiting for callback on port 8080...")

    httpd = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()

    server_done.wait(timeout=600)
    httpd.shutdown()

    if not auth_code:
        print("ERROR: No auth code received (timed out after 120s).")
        return

    print("Exchanging code for tokens...")
    tokens = exchange_code(auth_code)

    if "access_token" not in tokens:
        print(f"ERROR: Token exchange failed: {tokens}")
        return

    save_tokens(tokens)
    print("\nSetup complete. Run google_health_fetch.py to test data access.")


if __name__ == "__main__":
    main()
