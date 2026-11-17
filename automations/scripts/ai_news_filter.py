"""AI News filter: one headless Claude call decides keep or skip for each new post.

Claude sees title, source and opening text only, plus the criteria in
config/ai_news.yaml, and returns a JSON array. A post missing from the answer (or a
malformed answer) gets no decision, so it is asked again on the next run.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLAUDE = os.environ.get("PFC_CLAUDE") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")


def ask_claude(prompt):
    env = dict(os.environ)
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN") and (REPO / ".env").exists():
        for line in (REPO / ".env").read_text().splitlines():
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                env["CLAUDE_CODE_OAUTH_TOKEN"] = line.split("=", 1)[1].strip().strip("\"'")
    p = subprocess.run([CLAUDE, "-p", prompt, "--allowedTools", "", "--output-format", "text"],
                       capture_output=True, text=True, timeout=600, env=env, cwd="/tmp")
    if p.returncode != 0:
        raise RuntimeError(f"claude exit {p.returncode}: {(p.stderr or p.stdout).strip()[-300:]}")
    return p.stdout


def build_prompt(posts, criteria):
    items = [{"url": p["url"], "source": p["source"], "title": p.get("title", ""),
              "opening": (p.get("opening") or p.get("summary") or "")[:1200]} for p in posts]
    return ("You sort blog posts for a reading list. Criteria:\n\n" + criteria +
            "\n\nPosts (JSON):\n" + json.dumps(items, indent=1) +
            '\n\nAnswer with ONLY a JSON array, one object per post: '
            '{"url": "<url>", "keep": true|false, "reason": "<one short line>", '
            '"rank": <1 = the most useful kept post from its source, 2 the next...; omit when skipped>}')


def decide(posts, criteria, ask=ask_claude):
    """{url: {"keep": bool, "reason": str}} for the posts Claude answered."""
    if not posts:
        return {}
    try:
        raw = ask(build_prompt(posts, criteria))
        m = re.search(r"\[.*\]", raw, re.S)
        answer = json.loads(m.group(0)) if m else []
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        return {}
    wanted = {p["url"] for p in posts}
    out = {}
    for a in answer if isinstance(answer, list) else []:
        if isinstance(a, dict) and a.get("url") in wanted and isinstance(a.get("keep"), bool):
            out[a["url"]] = {"keep": a["keep"], "reason": str(a.get("reason", ""))[:200],
                             "rank": a["rank"] if isinstance(a.get("rank"), int) else 99}
    return out
