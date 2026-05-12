# Remote access — Termius + tmux + Claude Code Remote Control

This doc covers how to drive the PFC system from your phone (or any computer) by SSHing into a VPS where Claude Code is running. Recommended stack:

- **Termius** — polished SSH client with iOS / Android / desktop apps, key syncing, and a tap-friendly mobile keyboard.
- **tmux** — terminal multiplexer that keeps your Claude Code session alive across SSH drops, app backgrounding, and phone reboots.
- **Claude Code Remote Control** — Anthropic's mobile control surface that pairs with a running Claude Code instance over the web and gives you a smooth chat UI plus push notifications for approval prompts.

This is the access stack most "I want to run my PFC system from anywhere" users converge on. Pick the subset that matches your constraints — every piece is independently useful.

## Tier

**Tier 3 unlock.** Builds on `docs/install/vps.md` — you need a VPS running the PFC repo first. If you only run the system on your laptop, you don't need any of this.

---

## Why the three pieces

| Piece | What it solves |
|---|---|
| Termius | A real SSH terminal on your phone, no painful coding keyboard. Saves keys/hosts across devices. |
| tmux | Without it, every dropped SSH connection kills your Claude Code session. With it, you `tmux attach` and pick up exactly where you left off. |
| Remote Control | Lets you talk to a session through Anthropic's web/app UI instead of a terminal. Push notifications fire when Claude is waiting for your approval — so you can be away from the screen and still respond fast. |

You can run any one of these on its own. The combination is what makes "the PFC system lives on a VPS and I drive it from my phone" feel natural.

### When Termius is the better tool than Remote Control

Remote Control is the smoothest day-to-day surface, but **Termius is the better fit when:**

- **You're using auto mode.** Remote Control's surface may not expose the auto-mode toggle the same way the terminal does, depending on the version. If you want to drive long autonomous skill runs without per-step approval, attach via Termius to a tmux'd Claude Code session and toggle auto mode there. (If your version of Remote Control does support auto mode, great — use whichever feels better.)
- **You need to debug shell-level things** — read logs, edit files directly with `vi`/`nano`, inspect systemd timers, run one-off `jq` queries. Remote Control is great for chat; Termius is better for "I'm SSHed in, doing terminal stuff."
- **You want to attach/detach tmux sessions explicitly** — Termius respects the underlying tmux state. Remote Control abstracts the terminal away, which is what you want most of the time but not always.

Keep both installed. Use Remote Control as the default; reach for Termius when the situation calls for direct terminal access or auto-mode-heavy work.

---

## Step 1 — Set up SSH access on the VPS

If you already have key-based SSH working into the VPS, skip this step. Otherwise:

1. On your laptop: `ssh-keygen -t ed25519 -C "$(whoami)@$(hostname)"` if you don't already have a key.
2. Copy the public key to the VPS: `ssh-copy-id user@your-vps-host`.
3. Test: `ssh user@your-vps-host` should land you in a shell without prompting for a password.

Lock the VPS to key-auth only once it works (`/etc/ssh/sshd_config`: `PasswordAuthentication no`, then `sudo systemctl reload sshd`).

---

## Step 2 — Install Termius on your phone (and any other devices)

1. App store → search **Termius** → install. Free tier is enough for personal use; the paid tier syncs hosts/keys across devices.
2. Open Termius → **Hosts** → **New Host** → enter the VPS hostname, username, and import the SSH key (or paste it in directly).
3. Tap the host to connect. You should land in the VPS shell.

Termius's mobile keyboard adds rows for Esc, Ctrl, Tab, arrows — these are the keys you actually need in a terminal, instead of the standard alphabetic phone keyboard. This is the difference between "I can use this" and "this is unusable on a phone."

### Voice input on mobile (optional)

Out of the box, Termius blocks IME features like Gboard's voice input — the terminal view uses a strict input mode that rejects "composing text," which is how voice input is delivered. The error you'll see: *"This app doesn't support voice input."*

**Fix:** Termius **Settings → Experimental Keyboard Support** → enable. This swaps the strict terminal input mode for a more permissive one that accepts standard IME text, including voice.

Once enabled, two solid options:

- **Gboard voice** — tap the mic in Gboard, speak, text lands in the terminal. Free, ships with the phone, decent transcription.
- **Wispr Flow** (**recommended**) — paid voice keyboard with substantially better transcription, especially for technical terms, names, and run-on dictation. Worth the cost if you do a lot of phone-driven Claude Code work.

For PFC-heavy mobile use — running `/pfc-trello-inbox`, dictating long descriptions or insights, evening check-in reflections — Wispr Flow noticeably reduces the "fix the transcript" overhead vs. Gboard voice.

**Caveat:** "Experimental" is in the name for a reason. Terminal interaction through an IME isn't friction-free — autocomplete suggestions may appear, arrow/tab escape sequences can land oddly, and some quirks are model-dependent. Leave it on for chat-style Claude Code prompts; toggle it off if you need precise terminal editing (`vi`, complex shell pipelines).

---

## Step 3 — Install and run tmux on the VPS

On the VPS:

```bash
sudo apt install tmux            # Debian / Ubuntu
# or: sudo dnf install tmux      # Fedora / RHEL

# Start a named session for the PFC repo:
tmux new -s pfc

# Inside the session, change to the repo and start Claude Code:
cd ~/pfc
claude
```

To **detach** from the session (leaves it running): `Ctrl-b d`.
To **reattach** later: `tmux attach -t pfc`.
To **list sessions**: `tmux ls`.

The PFC pattern: one long-lived tmux session named `pfc` holding a Claude Code instance. You attach to it from Termius whenever you want to interact; you detach when you're done. The Claude Code session and any in-flight skill runs survive disconnects, reboots are the only thing that kills them (and even then, `tmux-resurrect` can save state — optional).

---

## Step 4 — Pair Claude Code Remote Control (optional)

Remote Control turns the tmux'd Claude Code instance into a phone-app chat experience. You get:

- A clean mobile UI on top of the same session.
- Push notifications when Claude is waiting for input.
- Multi-device handoff: start a conversation on the phone, finish it on the laptop.

Pairing is one slash command inside an active Claude Code session. The exact command and pairing UX evolves with Claude Code releases — run `claude --help` and look for the remote-control or pairing entries, or check the official Claude Code docs for the current invocation.

Once paired, the official Claude app on your phone will show the active session and let you continue from there.

**Caveat on auto mode:** Remote Control may or may not expose Claude Code's auto-mode toggle the same way the terminal does, depending on your Remote Control version. If you rely on auto mode for low-friction skill runs, verify the toggle works through Remote Control before relying on it. If it doesn't, attach via Termius for those sessions instead — the toggle always works in a normal terminal.

---

## Daily workflow

The pattern that drops the friction of "ugh I'm on my phone, I don't want to deal with this":

1. **Capture from phone via Trello widget** when away from the laptop (`docs/install/trello.md`).
2. **Process the inbox via Remote Control** when convenient: open Claude on the phone → say `/pfc-trello-inbox` → approve the proposed actions.
3. **Run morning- and evening-checkin from either Remote Control or Termius**, whichever surface is closer. Both hit the same tmux session.
4. **Use Termius for anything terminal-heavy** — debugging, log reading, manual edits.

---

## Troubleshooting

**SSH drops mid-skill and the session is gone.** You didn't run inside tmux. `tmux new -s pfc` first, then `claude`.

**Remote Control won't connect.** Verify the Claude Code session in tmux is fresh and re-pair. Confirm the VPS allows outbound HTTPS (the pairing flow uses Anthropic's infrastructure).

**Termius can't find the host.** Check your VPS provider's firewall and the VPS's `ufw status` — port 22 (or your custom SSH port) must be open.

**Push notifications don't arrive.** Check the Claude app's notification permissions on the phone OS.

---

## Cost summary

| Item | Cost |
|---|---|
| VPS | $4–6/month (Hetzner, DigitalOcean, Vultr — see `docs/install/vps.md`) |
| Termius | Free tier is enough for one device. Premium is ~$10/mo for multi-device sync — optional. |
| Claude Code Remote Control | Bundled with the Claude app; no separate cost. |
| tmux | Free. |

The minimum spend to run the full mobile-first PFC stack: a $4/mo VPS. Everything else is bundled or optional.
