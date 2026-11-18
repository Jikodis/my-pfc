# TRMNL polling endpoint (Tier 3)

Stands up the HTTPS endpoint TRMNL polls for plugin payloads. This is the
**preferred transport** — see [`docs/trmnl-plugins.md`](../trmnl-plugins.md) for why
polling beats webhook.

Optional. Skip this entire page if you don't own a TRMNL device, or if the webhook
fallback (no server needed) is enough for you.

**Prerequisite:** the VPS from [`vps.md`](vps.md), with the repo cloned at `~/pfc` and
systemd user units working.

## What gets built

```
TRMNL  ──HTTPS──►  Caddy :443            (TLS, automatic certs)
                     │  reverse_proxy
                     ▼
                   trmnl_serve.py :8765  (loopback only, bearer auth)
                     │  builds per request
                     ▼
                   the repo clone        (pfc-repo-sync.timer keeps it current)
```

Three properties matter and each is deliberate:

- **Loopback bind.** The Python process never faces the internet. Caddy is the only
  listener, so TLS and the public surface are its problem, not the app's.
- **Per-request builds.** No cache. TRMNL refreshes a plugin right before showing its
  screen, so a request-time build is what makes the wall current at a glance.
- **Bearer token.** `trmnl_serve.py` refuses to start without `TRMNL_SERVE_TOKEN`.
  An unauthenticated request gets 401 before the server reveals whether a plugin exists.

## Prerequisites

- The VPS from [`vps.md`](vps.md)
- A domain you control, and access to its DNS
- Ports 80 and 443 reachable (80 is needed for Let's Encrypt's HTTP-01 challenge)

Throughout this page, substitute your own values for:

| Placeholder | Meaning |
|---|---|
| `trmnl.example.com` | The subdomain you are pointing at the server |
| `203.0.113.10` | The server's public IPv4 address |
| `~/pfc` | Where you cloned the repo on the server |

## Step 1 — Point a subdomain at the server

In the DNS provider holding the zone, add one **A record**. Do this first and let it
propagate — Caddy cannot issue a certificate until the name resolves.

| Field | Value |
|---|---|
| Type | `A` |
| Host / Name | `trmnl` (some providers want the full `trmnl.example.com`) |
| Value / Points to | your server's IPv4 address |
| TTL | 300 — raise later; a low TTL makes a mistake cheap to fix |
| Proxy / CDN | **off** — Caddy must terminate TLS itself |

**No AAAA record unless the box really has public IPv6.** A dangling AAAA makes the
certificate challenge try IPv6 first and fail.

Verify from anywhere:

```sh
dig +short trmnl.example.com     # must return your server's IP
```

## Step 2 — Run this on the server

Paste to Claude on the server, or work through it by hand. It needs `sudo` for the
firewall and Caddy, so expect a password prompt.

````
Set up the TRMNL polling endpoint on this server. The repo is at ~/pfc.
Work through these in order and stop at the first one that fails, telling me what
broke rather than working around it.

1. Pull the repo: `git -C ~/pfc pull`

2. Check the firewall: `sudo ufw status verbose`. Report what it says BEFORE
   changing anything. If 80 and 443 are not allowed, add them:
       sudo ufw allow 80/tcp comment 'HTTP - ACME challenge'
       sudo ufw allow 443/tcp comment 'HTTPS - TRMNL polling endpoint'
   Do not change any other rule. If anything else is listening on a public
   interface, tell me about it but do NOT change it either way — closing a port
   I am using breaks my work with no warning.

3. Generate the bearer token and put it in .env:
       cd ~/pfc
       python3 automations/scripts/trmnl_serve.py --gen-token
   Append `TRMNL_SERVE_TOKEN=<the generated value>` to ~/pfc/.env.
   Print the token back to me once — I need it for the TRMNL plugin settings.
   Do not commit .env (it is gitignored).

4. Install the systemd units:
       ~/pfc/automations/systemd/install.sh
   This adds pfc-trmnl-serve.service (the endpoint) and pfc-repo-sync.timer
   (a 5-minute `git pull --ff-only` so served data tracks the remote).
   Confirm both are active:
       systemctl --user status pfc-trmnl-serve.service --no-pager
       systemctl --user list-timers pfc-repo-sync.timer --no-pager

5. Verify the endpoint locally before exposing it:
       curl -s http://127.0.0.1:8765/healthz
       curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/p/pfc-today
       curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/p/pfc-today
   Expect: `ok`, then `401`, then a JSON payload. If the third returns 500,
   show me `journalctl --user -u pfc-trmnl-serve -n 50 --no-pager`.

6. GATE — check DNS before touching Caddy:
       dig +short trmnl.example.com
   If that does not return the server's IP, STOP here and tell me. The record
   may not exist yet or may still be propagating. Caddy cannot issue a
   certificate until it resolves, and retrying just gets the domain rate-limited
   by Let's Encrypt. Everything through step 5 is still useful work — the
   endpoint runs locally and I can point Caddy at it later.

   Once DNS resolves, install Caddy (official apt repo) and configure it as the
   TLS front door:
       sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
       curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
         | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
       curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
         | sudo tee /etc/apt/sources.list.d/caddy-stable.list
       sudo apt update && sudo apt install -y caddy

   Then write /etc/caddy/Caddyfile with exactly this:

       trmnl.example.com {
           encode zstd gzip
           handle /p/* {
               reverse_proxy 127.0.0.1:8765
           }
           handle {
               respond "not found" 404
           }
       }

   Only /p/* is proxied — /healthz stays loopback-only so the public surface is
   just the payload routes. Reload and confirm the certificate was issued:
       sudo systemctl reload caddy
       sudo systemctl status caddy --no-pager
       journalctl -u caddy -n 30 --no-pager

7. Verify from outside the box:
       curl -s -o /dev/null -w '%{http_code}\n' https://trmnl.example.com/p/pfc-today
       curl -s -H "Authorization: Bearer $TOKEN" https://trmnl.example.com/p/pfc-today
   Expect 401 then the JSON payload. Report both results and the token.
````

## Step 3 — Point the plugin at it

In the TRMNL plugin's settings:

| Field | Value |
|---|---|
| Strategy | Polling |
| Polling URL | `https://trmnl.example.com/p/pfc-today` |
| Polling Verb | GET |
| Polling Headers | `Authorization: Bearer <TRMNL_SERVE_TOKEN>` |
| Polling Body | blank |

Headers are set in the TRMNL UI, never in `src/settings.yml` — `trmnlp push` would
round-trip the token through the repo, and TRMNL treats `polling_headers` as a
protected field for that reason.

Then hit **Force Refresh** on the plugin settings page to fetch immediately rather than
waiting for the device's next cycle.

## Adding a plugin later

The endpoint serves every builder registered in `BUILDERS`, so a new screen needs no
server change:

1. Add the builder to `automations/scripts/trmnl_home.py` and register it in `BUILDERS` in `automations/scripts/trmnl_push.py`
2. Commit and push; `pfc-repo-sync.timer` picks it up within 5 minutes
3. `systemctl --user restart pfc-trmnl-serve` on the server to load the new code
4. Point the new plugin at `https://trmnl.example.com/p/<plugin>`

## Hardening (optional)

TRMNL publishes its source IP addresses at [trmnl.com/api/ips](https://trmnl.com/api/ips).
You can add a Caddy matcher restricting `/p/*` to those, on top of the bearer token.

Worth knowing before you do: the list can change without notice, and when it does the
screen silently stops updating. The bearer token is the real control. Treat an IP
allowlist as defense in depth you have signed up to maintain, not a substitute.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Caddy cannot get a certificate | DNS not propagated, port 80 blocked, or a dangling AAAA record |
| `401` with the right token | Token in `.env` and in the plugin's polling headers differ — regenerate and set both |
| `500` from `/p/<plugin>` | Builder threw; `journalctl --user -u pfc-trmnl-serve -n 50` has the trace |
| Payload is stale | `systemctl --user list-timers pfc-repo-sync.timer`, then `journalctl --user -u pfc-repo-sync -n 20` — a `--ff-only` failure means the server has unpushed commits |
| Screen unchanged despite fresh payload | TRMNL skips regeneration when merge variables are identical. Force Refresh overrides. |
