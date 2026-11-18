---
name: pfc-repo-maintenance
description: Audit the repo's plumbing and documentation for drift, gaps, or broken references — not life content. Use when the user says "repo maintenance", "maintenance check", "repo audit", "docs audit", "clean the repo", "docs check", or before a structural change. This is NOT /pfc-usage-audit (whether the system is being used and producing) and NOT /pfc-status (content view).
---

# Repo Maintenance

Verify the machinery and docs are clean, accurate, and coherent. Fix trivial drift autonomously; surface judgment calls to the user.

## Scope

| Domain | Checked |
|---|---|
| **Validation** | `scripts/validate.sh` (NDJSON parse, schema lint, skill frontmatter) |
| **Cross-file integrity** | task.project → projects.ndjson; task.depends_on → tasks.ndjson or tasks-archive.ndjson (no self-reference); daily-focus ids → tasks.ndjson; habit.area → `2-areas/`; project.area → `2-areas/`; insight.area → `2-areas/`; insight.graduated_to (when set) resolves to a real task/project/habit; finding.source_hypothesis_id → hypotheses.ndjson; finding.superseded_by → findings.ndjson; supplements.ndjson active `started` date not in the future; supplements.ndjson schema referenced in `docs/data-model.md`; insights.ndjson + insight_schema referenced in `docs/data-model.md`; habits-daily.ndjson: any record with `skipped:true` must have `completed:false` and a non-empty `skip_reason`; tasks.ndjson: any record with `deferred:true` must have `status:"open"` and a non-empty `deferred_reason` (a done task cannot be parked, and a park with no stated reason is unrecoverable at un-park time); focus.area → `2-areas/` and the pursuit cap ≤6 (both covered by validator §14 — reference it, don't re-implement); focus.link.ref (when set) resolves to a vision slug / habit id / project id; grounding.area (when set) → `2-areas/` |
| **Orphans** | Scripts called by no skill; skills referencing missing files/scripts; empty NDJSON files referenced in skills |
| **Stale** | tasks.ndjson > 200 lines; done tasks not archived; unpushed commits; docs untouched 90+ days; expected notes subdirectories (`notes/daily/`, `notes/yearly/`) exist (`notes/weekly/` + `notes/monthly/` are archival — the ritual weekly/monthly check-ins were replaced by the rolling-review ledger, so nothing writes there anymore and they are not required) |
| **Docs accuracy** | AGENTS.md claims vs reality; every data/ file documented in `docs/data-model.md`; every skill listed exists; no contradictions between AGENTS.md and `docs/`; no `CLAUDE.md` or `CLAUDE.local.md` tracked anywhere in the repo (AGENTS.md is the only instruction file); `data/findings.ndjson` and `config/finding_schema.yaml` both present in `docs/data-model.md`; `data/supplements.ndjson` and `config/supplement_schema.yaml` both present in `docs/data-model.md`; `data/hypotheses.ndjson` and `config/hypothesis_schema.yaml` both present in `docs/data-model.md`; `4-focus/_data/focus.ndjson` + `config/focus_schema.yaml` + `config/focus.yaml` all present; `data/grounding.ndjson` + `config/grounding_schema.yaml` both present; `data/review-ledger.ndjson` + `config/review_ledger_schema.yaml` both present |
| **Docs coverage** | Every active skill has a trigger phrase; every cadence in `docs/cadences.md` maps to a skill; every config file has a doc reference |
| **Mirrored-list drift** | Lists in `docs/` that are mirrored from AGENTS.md (commit conventions, auto-commit, ask-before-commit) match verbatim |
| **Bare-path references** | Unlinked path mentions in prose (e.g. `notes/`, `data/foo.ndjson`) resolve to real files/directories |
| **Tool-usage contradictions** | No doc recommends a tool that AGENTS.md forbids (e.g. `sed`/`echo >>` on NDJSON) |
| **Deprecated vocabulary** | No doc still references deleted files or removed concepts |
| **Env-var coverage** | Every var declared in `.env.example` is referenced by at least one script or skill; vars referenced in scripts/skills exist in `.env.example`. `.env` populating is informational only — never a failure. |
| **pfc-revive plumbing** | `data/revive-events.ndjson` exists and parses (validator §13); `config/revive_event_schema.yaml` exists; `automations/scripts/revive_watchlist.py` exists and runs cleanly against the live repo; integration references intact — `pfc-evening-checkin` SKILL.md cites `revive_watchlist.py` (the `stale-task-triage` gate in Step 3c) and `pfc-revive` (the owning-skill map), `pfc-review` SKILL.md cites `revive_watchlist.py` (the `stale-task-triage` form's rows), AGENTS.md mentions `pfc-revive` |
| **Rolling-review wiring** | Every id in `data/review-ledger.ndjson` has a `case` branch in the `gate()` block of `pfc-evening-checkin` Step 3c, a row in that step's owning-skill map, AND a row in the form table of `pfc-review` — and none of the three names an id the ledger doesn't have. A ledger id with no gate never surfaces, a gate with no ledger id is dead code, a surfaced id with no map row leaves the user with no next step, and a review with no form row cannot be done one at a time |
| **Current Focus plumbing** | `4-focus/_data/focus.ndjson` parses (validator §14); `config/focus_schema.yaml` + `config/focus.yaml` exist; the pursuit cap in `config/focus.yaml` matches the cap the validator and `automations/scripts/trello_render.py` enforce; `4-focus/README.md` + `4-focus/AGENTS.md` both present |
| **Front-of-Mind plumbing** | `data/grounding.ndjson` parses (validator §16); `config/grounding_schema.yaml` exists; the `soft_cap.active_records` value in the schema matches `GROUNDING_CAP` in `automations/scripts/trello_render.py` |
| **TRMNL plumbing** | Every folder under `trmnl/` (except `bin/`) has `.trmnlp.yml` + `src/settings.yml` + `src/full.liquid`; every plugin folder has a matching key in `BUILDERS` in `automations/scripts/trmnl_push.py` and vice versa (a folder with no builder never updates its screen; a builder with no folder is dead code); every plugin appears in the tables in `docs/trmnl-plugins.md` and `trmnl/README.md`; no `_build/` output is tracked by git; no `polling_url:` / `polling_headers:` **key** appears in any `src/settings.yml` (the header carries a bearer token and `trmnlp push` would round-trip it into the repo); `TRMNL_SERVE_TOKEN` is declared in `.env.example`; `.claude/settings.json` still declares the `trmnl` plugin under both `extraKnownMarketplaces` and `enabledPlugins`; framework hard rules hold in `trmnl/**/*.liquid` (no `style="`, no `<style>`, no emoji, no `usetrmnl.com` URLs); `data/calendar-cache.json` (when present) parses and has `fetched_at` + `events` |
| **reMarkable plumbing** (skip when not set up) | `automations/scripts/remarkable_{pages,lines,sync,replies}.py` exist and `python3 -m pytest automations/scripts/tests/test_remarkable.py` passes (it skips without Pillow); `PAGE_NAMES` in `remarkable_pages.py` is the inbox page, one page per group of the web home page (Today, This quarter, Always), the review page, then the task list, and each page draws that group's bands in the web page's order (a band added to or removed from `web/src/pages/index.astro` needs the same change there); every `kind` a page marks (`rating`, `task`, `habit`, `swap`, `pick`, `park`, `drop`, `task-note`, `note`, `area`, `inbox`, `review-row`, `review-prompt`, `review-skip`) is handled in `plan_writes` and maps to a `web_write.py` command, an inbox card or `/pfc-review`; `remarkable_replies.PAGES` equals `PAGE_NAMES`; `install.sh` lists `pfc-remarkable-sync.{service,timer}` in `UNITS`; `data/.remarkable/` is in `.gitignore`; `docs/remarkable.md` matches the page table. |
| **AI News plumbing** (skip when not set up) | `automations/scripts/ai_news*.py` exist and `python3 -m pytest automations/scripts/tests/test_ai_news.py` passes; `config/ai_news.yaml` parses and every source has `id`, `name`, `method` (`rss` or `index`) and `url` (an `index` source also `link`); `data/ai-news.ndjson` passes validator §18 and is in `AGENT_ONLY_DATA` in `web/src/lib/data-files.ts`; `install.sh` lists `pfc-ai-news.{service,timer}`; `data/.ai-news/` is in `.gitignore`; the `/p/pod/` route in `trmnl_serve.py` still refuses a wrong secret and a path outside the feed folder (the test covers it). |
| **Area note indexes** | For every `2-areas/<area>/AGENTS.md` that exists, the rows in its Contents table match the `.md` files actually in that folder (excluding `statement.md` and `AGENTS.md` itself). Area folders ship without an index — an absent index is not a finding, a stale one is |
| **Area items plumbing** | `2-areas/_data/area-items.ndjson` and `area-checkins.ndjson` conform to `config/area_item_schema.yaml` (validator §17: ids unique, areas resolve, `habit:<id>` sources declared, every check-in `item_id` resolves); both files and the schema are documented in `docs/data-model.md` and `2-areas/AGENTS.md`; `python3 automations/scripts/area_items.py` runs cleanly against the live repo (it is what `/pfc-status` and the `life-wheel` review read) |
| **Tests** | `python3 -m pytest automations/scripts/tests scripts/tests -q` passes (always `python3 -m pytest`, never a bare `pytest`, so the tests run under the same interpreter the scripts use); the Bash permission hook (`scripts/hook-allow-known-commands.py`) is registered under `PreToolUse` in `.claude/settings.json` |

## Steps

1. **Run the mechanical validator:**
   ```bash
   scripts/validate.sh
   ```
   If red, stop and surface errors. Do not proceed to other checks until it's green.

2. **Cross-file integrity:**
   ```bash
   # Tasks referencing projects that don't exist
   comm -23 \
     <(jq -r 'select(.project != "none" and .project != null) | .project' 6-tasks/_data/tasks.ndjson | sort -u) \
     <(jq -r '.id' 5-projects/_data/projects.ndjson | sort -u)

   # Daily-focus task ids that don't exist in tasks.ndjson (live or archive)
   jq -r '.critical[]?, .bonus // empty' 6-tasks/_data/daily-focus.ndjson | sort -u > /tmp/focus-ids
   jq -r '.id' 6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson | sort -u > /tmp/task-ids
   comm -23 /tmp/focus-ids /tmp/task-ids

   # Findings → hypotheses: source_hypothesis_id must resolve
   comm -23 \
     <(jq -r 'select(.source == "hypothesis") | .source_hypothesis_id' data/findings.ndjson | sort -u) \
     <(jq -r '.id' data/hypotheses.ndjson | sort -u)

   # Findings → findings: superseded_by must resolve
   comm -23 \
     <(jq -r 'select(.status == "superseded") | .superseded_by' data/findings.ndjson | sort -u) \
     <(jq -r '.id' data/findings.ndjson | sort -u)

   # Supplements registry: no active record with started in the future
   TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
   jq -r --arg t "$TODAY" 'select(.status == "active" and .started > $t) | .id' data/supplements.ndjson

   # habits-daily: skipped:true must have completed:false and non-empty skip_reason
   # tasks: deferred:true must be open and carry a reason
   jq -c 'select(.deferred == true and (.status != "open" or (.deferred_reason // "") == ""))' \
     6-tasks/_data/tasks.ndjson

   jq -c 'select(.skipped == true and (.completed != false or (.skip_reason // "") == ""))' \
     7-habits/_data/habits-daily.ndjson

   # Insights → graduated_to: must resolve to a real task, project, or habit
   if [ -s data/insights.ndjson ]; then
     jq -r 'select(.status == "graduated") | .graduated_to' data/insights.ndjson | sort -u | while read -r tid; do
       [ -z "$tid" ] && continue
       case "$tid" in
         task-*) jq -e --arg t "$tid" 'select(.id == $t)' 6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson >/dev/null 2>&1 || echo "insight graduated_to unresolved task: $tid" ;;
         proj-*) jq -e --arg t "$tid" 'select(.id == $t)' 5-projects/_data/projects.ndjson >/dev/null 2>&1 || echo "insight graduated_to unresolved project: $tid" ;;
         *)      grep -qE "^[[:space:]]*-[[:space:]]*id:[[:space:]]*[\"']?$tid[\"']?" config/habit_schema.yaml || echo "insight graduated_to unresolved habit_id: $tid" ;;
       esac
     done
   fi

   # focus.link.ref must resolve to its declared type (vision slug / habit id / project id).
   # focus.area and the ≤6 pursuit cap are already validator §14 — do not re-implement them here.
   if [ -s 4-focus/_data/focus.ndjson ]; then
     jq -rc 'select(.link != null) | "\(.link.type)\t\(.link.ref)"' 4-focus/_data/focus.ndjson | \
     while IFS=$'\t' read -r lt ref; do
       case "$lt" in
         vision)  [ -f "3-visions/$ref.md" ] || echo "focus link → missing vision: $ref" ;;
         habit)   grep -qE "^[[:space:]]*-[[:space:]]*id:[[:space:]]*[\"']?$ref[\"']?" config/habit_schema.yaml \
                    || echo "focus link → missing habit: $ref" ;;
         project) jq -e --arg r "$ref" 'select(.id==$r)' 5-projects/_data/projects.ndjson >/dev/null 2>&1 \
                    || echo "focus link → missing project: $ref" ;;
       esac
     done
   fi

   # grounding.area (when set) must match a 2-areas/ folder
   if [ -s data/grounding.ndjson ]; then
     jq -r 'select((.area // "") != "") | .area' data/grounding.ndjson | sort -u | while read -r a; do
       [ -d "2-areas/$a" ] || echo "grounding area does not exist: $a"
     done
   fi

   # Schema soft caps must match the code that enforces them
   SCHEMA_CAP=$(awk '/^soft_cap:/{f=1;next} f && /active_records:/{print $2; exit}' config/grounding_schema.yaml)
   CODE_CAP=$(grep -oE '^GROUNDING_CAP *= *[0-9]+' automations/scripts/trello_render.py | grep -oE '[0-9]+')
   [ "$SCHEMA_CAP" = "$CODE_CAP" ] || echo "grounding soft cap drift: schema=$SCHEMA_CAP code=$CODE_CAP"
   ```
   For each broken reference, report: file, id, what's missing. Ask before deleting.

3. **Orphan detection:**
   - For each `automations/scripts/*.py` and `automations/scripts/*.sh`: grep `.agents/skills/*/SKILL.md`, `automations/**/README.md`, and `automations/scripts/*` (for cross-imports) for the filename. Unreferenced scripts are orphans. **Exclude:** anything under `automations/scripts/tests/` (test files are expected to not be skill-referenced).
   - For each file path mentioned in a skill (`data/*.ndjson`, `config/*.yaml`, `automations/scripts/*`): verify the file exists. Skip placeholder example paths in this skill itself (e.g. `data/foo.ndjson` mentioned in the table of contents).
   - For each NDJSON file in `data/`: if it's empty AND not written by any skill, flag for deletion.

4. **Stale detection:**
   ```bash
   test $(wc -l < 6-tasks/_data/tasks.ndjson) -gt 200 && echo "tasks.ndjson over 200 lines — run archive"
   jq -c 'select(.status == "done")' 6-tasks/_data/tasks.ndjson | wc -l  # done tasks still in live file
   git log origin/main..HEAD --oneline                          # unpushed commits
   find docs -name '*.md' -mtime +90                            # docs older than 90 days
   # Notes subdirectory structure — daily + yearly are actively written and must exist.
   # (weekly/ + monthly/ are archival: the ritual weekly/monthly check-ins were replaced
   # by the rolling-review ledger, so nothing writes there. Their absence is not a finding.)
   for d in notes/daily notes/yearly; do
     [ -d "$d" ] && echo "notes_dir:OK:$d" || echo "notes_dir:MISSING:$d"
   done
   # Git hooks installed — every file in .githooks/ must be present and executable at .git/hooks/
   for src in .githooks/*; do
     name=$(basename "$src")
     dst=".git/hooks/$name"
     if [ ! -x "$dst" ]; then
       echo "hook:MISSING:$name (install: cp .githooks/$name .git/hooks/ && chmod +x .git/hooks/$name)"
     elif ! cmp -s "$src" "$dst"; then
       echo "hook:STALE:$name (versioned source differs from installed copy)"
     else
       echo "hook:OK:$name"
     fi
   done
   # Bash permission hook registered in .claude/settings.json
   jq -e '.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[] | select(.command | endswith("scripts/hook-allow-known-commands.py"))' .claude/settings.json >/dev/null \
     && echo "hook:OK:allow-known-commands registered" || echo "hook:MISSING:allow-known-commands (PreToolUse Bash entry in .claude/settings.json)"
   # Script and hook tests. Always python3 -m pytest, never a bare pytest.
   python3 -m pytest automations/scripts/tests scripts/tests -q >/dev/null 2>&1 \
     && echo "tests:OK" || echo "tests:FAIL (run python3 -m pytest automations/scripts/tests scripts/tests -q)"
   ```

5. **Docs gardening:**
   - **AGENTS.md accuracy**: for each skill listed, confirm it exists; for each file path mentioned, confirm it exists; for each rule (e.g. the active-project backstop, the Current Focus pursuit cap), confirm docs and schemas agree.
   - **docs/data-model.md coverage**: every file in `data/*.ndjson` must appear in the doc. Every field used in the actual records must appear in the doc (use `jq -s 'map(keys)|flatten|unique'` per file to find gaps). For `config/`, every committed file must appear; **skip gitignored files** (use `git check-ignore` to filter — auth artifacts like `google_health_tokens.json` are local-only). The registries that live outside `data/` are easy to miss — check them by name:
     ```bash
     for f in 4-focus/_data/focus.ndjson config/focus_schema.yaml config/focus.yaml \
              data/grounding.ndjson config/grounding_schema.yaml \
              data/review-ledger.ndjson config/review_ledger_schema.yaml \
              data/revive-events.ndjson config/revive_event_schema.yaml \
              data/calendar-cache.json; do
       grep -qF "$(basename "$f")" docs/data-model.md \
         && echo "data-model:OK:$f" || echo "data-model:MISSING:$f"
     done
     ```
   - **Skill coverage**: every `.agents/skills/*/` must have `SKILL.md` with frontmatter matching directory name (validator already checks); every cadence named in `docs/cadences.md` should have a skill or explicit automation.
   - **Contradictions**: grep both AGENTS.md and `docs/` for the same key facts (max projects, id formats, field names). Report any mismatches.
   - **Dead links**: grep all `.md` for `](./...)` or `](../...)` paths and verify each resolves.

   - **No `CLAUDE.md` anywhere.** AGENTS.md is the only instruction file (root and any subfolder that needs one). Claude Code reads `AGENTS.md` natively, and a `CLAUDE.md` at or above the working directory switches that off, so nested `AGENTS.md` files stop loading.
     ```bash
     [ -z "$(git ls-files | grep -E '(^|/)(CLAUDE|CLAUDE\.local)\.md$')" ] \
       && echo "no CLAUDE.md in repo:OK" || echo "CLAUDE.md found (move its rules into AGENTS.md, then delete it):FAIL"
     ```

   - **Area note indexes**: area folders ship without an index and gain a `2-areas/<area>/AGENTS.md` lazily when the first note lands (see `2-areas/AGENTS.md`). Where one exists, its Contents table must list exactly the note files in that folder. A missing index is not a finding; a stale one is.
     ```bash
     for idx in 2-areas/*/AGENTS.md; do
       [ -f "$idx" ] || continue
       dir=$(dirname "$idx")
       ls "$dir"/*.md 2>/dev/null | xargs -n1 basename \
         | grep -vE '^(statement|AGENTS)\.md$' | sort -u > /tmp/area-files
       grep -oE '`[A-Za-z0-9_-]+\.md`' "$idx" | tr -d '`' | sort -u > /tmp/area-rows
       echo "--- $dir: files with no index row ---"; comm -23 /tmp/area-files /tmp/area-rows
       echo "--- $dir: index rows with no file ---"; comm -13 /tmp/area-files /tmp/area-rows
     done
     ```

   - **Mirrored-list drift** — AGENTS.md is canonical; secondary docs that mirror its lists must match verbatim. Known mirrors:

     | AGENTS.md section | Mirror location |
     |---|---|
     | "Auto-commit" bullets under Commit policy | `docs/automation-policy.md` "Auto-commit operations" |
     | "Ask before committing" bullets | `docs/automation-policy.md` "Ask-before-commit operations" |
     | "Commit message conventions" bullets | `docs/conventions.md` "Commit messages" |

     For each pair, extract the bulleted lines from both files and diff. The `awk '/start/,/end/'` range form does NOT work here — when the start pattern's prefix (e.g. `^### `) also matches the start line, the range opens and closes on the same line and returns nothing. Use a flag-toggle pattern instead:
     ```bash
     # Compare auto-commit lists (AGENTS.md is canonical)
     awk '/^### Auto-commit \(no confirmation needed\)$/{f=1;next} /^### /{f=0} f' AGENTS.md \
       | grep -E '^- ' | sort > /tmp/canonical.txt
     awk '/^## Auto-commit operations \(no confirmation needed\)$/{f=1;next} /^## /{f=0} f' \
       docs/automation-policy.md | grep -E '^- ' | sort > /tmp/mirror.txt
     diff /tmp/canonical.txt /tmp/mirror.txt
     ```
     Any asymmetric diff → update the mirror (AGENTS.md is canonical).

   - **Bare-path verification** — unlinked path references in prose should resolve. Grep the live docs:
     ```bash
     grep -rnE '\b(data|config|0-me|1-values|2-areas|3-visions|4-focus|5-projects|6-tasks|7-habits|notes|trmnl|automations)/[A-Za-z0-9_.-]+' \
       --include='*.md' \
       AGENTS.md README.md docs/ 0-me/ 1-values/ 2-areas/AGENTS.md trmnl/AGENTS.md \
       4-focus/AGENTS.md 5-projects/AGENTS.md 6-tasks/AGENTS.md 7-habits/AGENTS.md data/AGENTS.md \
       | grep -oE '\b(data|config|0-me|1-values|2-areas|3-visions|4-focus|5-projects|6-tasks|7-habits|notes|trmnl|automations)/[A-Za-z0-9_./-]+' \
       | grep -vE 'YYYY|MM|NN|/\.[a-z_]+\.tmp$|XX|<area>|<slug>|<plugin>|<area-folder-name>|^config/rmapi/|^data/\.(remarkable|ai-news)/' \
       | sort -u
     ```
     Keep the folder alternation in **both** `grep` expressions in sync with the live top-level layout (`4-focus/` is easy to forget — it was the last VAVFPTH folder added). A folder missing from the alternation means every bare path under it goes unchecked.
     For each path extracted, `test -e` to confirm it exists. Report misses. The `grep -vE` filter drops template placeholders (`YYYY-MM-DD`, `WNN`, `<slug>`) and jq tempfile names (`data/.jq_update.tmp`) — these are *intentional* non-existent paths in conventions and code examples, not drift. `^config/rmapi/` drops the tail of `~/.config/rmapi/rmapi.conf` (the reMarkable sign-in on the server, never a repo path), and `^data/\.(remarkable|ai-news)/` the git-ignored state folders those optional jobs create at run time.

   - **Tool-usage contradictions** — AGENTS.md forbids certain tools on structured data. Grep secondary docs for the forbidden forms:
     ```bash
     grep -rnE 'via sed|sed.*ndjson|echo.*>>.*\.ndjson|sed -i.*ndjson' \
       --include='*.md' docs/ AGENTS.md 0-me/ 1-values/ README.md trmnl/AGENTS.md \
       4-focus/AGENTS.md 5-projects/AGENTS.md 6-tasks/AGENTS.md 7-habits/AGENTS.md data/AGENTS.md \
       | grep -vE 'forbidden|never|do not|no raw'
     ```
     Preferred form for any NDJSON edit is `jq` with a temp file. Flag any remaining recommendation of `sed`, `awk -i`, `echo >>`, or raw `>>` appends targeting NDJSON.

   - **Env-var coverage** — every var in `.env.example` should be referenced by at least one script or skill, and every env var read by a script/skill should be declared in `.env.example`. Tracked vars currently include `LOCAL_TZ`, `CLAUDE_CODE_OAUTH_TOKEN`, `GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`, `GOOGLE_HEALTH_TOKEN_FILE`, `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_INBOX_LIST_ID`, `TRELLO_DASHBOARD_BOARD_ID`, `TRMNL_API_KEY`, `TRMNL_SERVE_TOKEN`. Trello credentials back the `pfc-trello-inbox` skill via `automations/scripts/trello_helper.py`, the `pfc-render-trello` skill via `automations/scripts/trello_render.py`, and the `pfc-sync-trello` skill via `automations/scripts/trello_writeback.py`. The TRMNL vars back `automations/scripts/trmnl_push.py` (webhook fallback) and `trmnl_serve.py` (the polling endpoint). The commented-out optional vars in `.env.example` (`TRMNL_SERVE_PORT`, `TRMNL_WEBHOOK_<PLUGIN>`, `TRMNL_PAYLOAD_LIMIT`, `TRMNL_CONTAINER_RUNTIME`, `TRMNL_COLOR_DEPTH`) are documentation for optional overrides, not declarations — the `^[A-Z_]` grep below skips them by design, so don't "fix" them into uncommented empty values. Whether `.env` itself has values populated is **informational only** — the audit never fails on missing local secrets.
     ```bash
     # Vars declared in .env.example
     grep -oE '^[A-Z_][A-Z0-9_]*=' .env.example | sed 's/=$//' | sort -u > /tmp/env-declared.txt
     # Vars actually referenced in code/skills
     grep -rohE '\b[A-Z_]{4,}[A-Z0-9_]*\b' automations/scripts/ .agents/skills/ \
       | grep -E '^(CLAUDE_CODE|GOOGLE_HEALTH|TRELLO|TRMNL)_' | sort -u > /tmp/env-used.txt
     # Declared but not referenced — THIS is the direction that matters. Expect empty.
     comm -23 /tmp/env-declared.txt /tmp/env-used.txt
     # Referenced but not declared — informational only, expect noise (see below)
     comm -13 /tmp/env-declared.txt /tmp/env-used.txt
     ```

     **Read the two directions differently.** "Declared but not referenced" is a real signal — a var in `.env.example` that nothing reads is dead config. "Referenced but not declared" is noise by construction, and hits on it are almost never drift: the `[A-Z_]{4,}` grep can't tell an env var from a module constant (`TRMNL_DIR`, `TRELLO_CARDS` are Python globals), and `grep -oE '^[A-Z_]*='` only sees *uncommented* lines in `.env.example`, so every optional var documented as a commented example reads as undeclared. Before reporting anything from this direction, confirm it's actually read via `os.environ`/`env.get` **and** genuinely absent from `.env.example` including comments. **Keep the prefix alternation in the grep in sync with the tracked-vars list above** — a var whose prefix is missing from the pattern reports as "declared but unreferenced" on every run, which trains the reader to ignore the check.

   - **Deprecated vocabulary** — concepts removed from the system should not still be referenced in live docs. Current list:

     | Old | New | Why |
     |---|---|---|
     | `pfc-morning-checkin` | — | Deleted. The daily spine is `pfc-evening-checkin`; there is no morning ritual. |
     | `pfc-weekly-checkin` | `pfc-evening-checkin` Step 3c + `/pfc-review` | Deleted. Weekly review work became rolling-ledger items that drip ≤2 per evening. |
     | `pfc-monthly-checkin` | `pfc-evening-checkin` Step 3c + `/pfc-review` | Deleted. Same ledger; monthly-cadence items. |
     | `📧 Email Priorities` (Trello list) | email→task pipeline | Replaced. Labeled inbox emails auto-create tasks via `pfc-email-triage` Step 0; there is no rendered email list. |
     | `passion-brainstorm` | `3-visions/_data/vision-brainstorm.ndjson` + `/pfc-vision-brainstorm` | Renamed. The markdown file is gone; the exercise is a skill writing NDJSON. |
     | `daily_pulse` (module) | `pulse` (`automations/scripts/pulse.py`) | Renamed. Any `import daily_pulse` / `from daily_pulse` is dead. |
     | ✅ calendar completion-sync | Trello Mark Complete + `/pfc-sync-trello` | Retired. Focus completion is never inferred from a calendar-event title marker. |
     | `4-focus` living in `data/focus.ndjson` | `4-focus/_data/focus.ndjson` | Moved when the Focus layer got its own VAVFPTH folder. |
     | `pfc-learned` (TRMNL plugin + builder) | — | Deleted — surfaced too much; insights/findings review lives in the check-in ledger. |
     | `pfc-slipping` (TRMNL plugin + builder) | `pfc-back-on-track` | Reworked into the off-track intentions screen (focus/projects/habits + re-entry steps; task watchlist dropped). |
     | `life_event` field (day-tracking) | — | Deleted. Days are never tagged or dropped for what happened in them. |
     | `pfc-system-health` (skill) + ledger id `system-health` | `pfc-usage-audit` / `usage-audit` | Renamed — the description now says what it audits (usage, not machinery). |
     | `6-actions/` folder | `6-tasks/` | Renamed: the Actions layer is now called Tasks. |
     | `VAVFPAH` (acronym) | `VAVFPTH` | Renamed with the layer (Actions → Tasks). |
     | `✅ Actions` (Trello list) | `✅ Tasks` | Renamed with the layer. |
     | `CLAUDE.md` (root, subfolder `@AGENTS.md` shims, `2-areas/<area>/CLAUDE.md` indexes) | `AGENTS.md` | Deleted. AGENTS.md is the only instruction file; area indexes are `2-areas/<area>/AGENTS.md`. Covered by the no-`CLAUDE.md` check above, not the grep (the name stays in prose that explains the rule). |

     ```bash
     grep -rnE 'pfc-morning-checkin|pfc-weekly-checkin|pfc-monthly-checkin|Email Priorities|render_email|--email-data|passion-brainstorm|daily_pulse|\bdata/focus\.ndjson|pfc-learned|build_pfc_learned|pfc-slipping|build_pfc_slipping|pfc-system-health|\b6-actions/|\bVAVFPAH\b|✅ Actions' \
       --include='*.md' --include='*.py' \
       AGENTS.md README.md docs/ 0-me/ 1-values/ 2-areas/ 3-visions/ trmnl/ \
       .agents/skills/ automations/scripts/ \
       4-focus/AGENTS.md 5-projects/AGENTS.md 6-tasks/AGENTS.md 7-habits/AGENTS.md data/AGENTS.md
     ```

     The `\b` before `data/focus.ndjson` is required — without it the pattern also matches inside `4-focus/_data/focus.ndjson` and every correct path reads as a hit.

     Expected exceptions: this skill file itself contains the table and the grep — that's the registry, not drift. `AGENTS.md` carries one deliberate mention of "Email Priorities" in the sentence explaining that the list no longer exists; a mention *about* the removal should stay. The `pfc-usage-audit` skill's one "renamed from `pfc-system-health`" line is likewise a mention about the rename. `pfc-pull-template-updates` names `6-actions/`, `VAVFPAH`, `✅ Actions` and `CLAUDE.md` on purpose: it carries the migration steps for older copies of the system.

     `life_event` is deliberately **not** in the grep. Surviving mentions (in `pfc-evening-checkin`, `pfc-log-day`, `pfc-analyze-trends`, `docs/data-model.md`) are load-bearing "do NOT tag or discount days for external events" guardrails, not drift — the rule has to stay stated or the behavior creeps back. What the audit should catch instead is *reintroduction*: `jq -e 'has("life_event")' data/day-tracking.ndjson` must find nothing.

     Report any hits. **When deleting a file or concept, append a row here and extend the grep** so future audits catch lingering references.

   - **Onboarding feature-catalog drift** — ensure every feature mentioned in pfc-onboarding's catalog (Step 3: Feature catalog table) corresponds to a real skill (or documented integration), and every shipped skill appears in the catalog.

     ```bash
     # Extract feature keys from the onboarding skill
     grep -oE '\b[a-z][a-z0-9-]+/[a-z][a-z0-9-]+\b' .agents/skills/pfc-onboarding/SKILL.md \
       | grep -E '^(daily-loop|tracking|knowledge|health|reviews|areas|visions|integrations|meta)/' \
       | sort -u > /tmp/catalog-keys

     # Extract skill names from the live tree
     ls .agents/skills/ | grep '^pfc-' | sort -u > /tmp/live-skills

     echo "=== Catalog keys ===" && cat /tmp/catalog-keys
     echo ""
     echo "=== Live skills ===" && cat /tmp/live-skills
     echo ""
     echo "Eyeball: every catalog key should map to a real skill or documented integration. Every live skill should appear in some lesson."
     ```

     This v1 audit prints both lists side-by-side for manual eyeballing. Full automated cross-check deferred until catalog stabilizes.

6. **pfc-revive plumbing:**

   Verify the revive-watchlist machinery is intact end-to-end.

   ```bash
   # (a) Data file exists and parses (validator §13 also covers this — this is the docs-side cross-check)
   [ -f data/revive-events.ndjson ] && echo "revive-events.ndjson:OK" || echo "revive-events.ndjson:MISSING"
   if [ -s data/revive-events.ndjson ]; then
     jq -c '.' data/revive-events.ndjson > /dev/null && echo "revive-events.ndjson:PARSES" || echo "revive-events.ndjson:PARSE-FAIL"
   fi

   # (b) Schema present
   [ -f config/revive_event_schema.yaml ] && echo "revive_event_schema.yaml:OK" || echo "revive_event_schema.yaml:MISSING"

   # (c) Watchlist script exists AND runs cleanly against live repo
   if [ -x automations/scripts/revive_watchlist.py ] || [ -f automations/scripts/revive_watchlist.py ]; then
     echo "revive_watchlist.py:OK"
     TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
     if python3 automations/scripts/revive_watchlist.py --today "$TODAY" >/dev/null 2>&1; then
       echo "revive_watchlist.py:RUNS"
     else
       echo "revive_watchlist.py:RUN-FAIL"
     fi
   else
     echo "revive_watchlist.py:MISSING"
   fi

   # (d) Integration references intact. The watchlist is wired into the evening
   #     check-in twice (the `stale-task-triage` gate calls the script, and the
   #     owning-skill map points the user at /pfc-revive), and /pfc-review builds
   #     the stale-task-triage form's rows from it. All of these must survive.
   grep -q 'revive_watchlist\.py' .agents/skills/pfc-evening-checkin/SKILL.md \
     && echo "evening-checkin→revive_watchlist.py:OK" \
     || echo "evening-checkin→revive_watchlist.py:MISSING"
   grep -q 'pfc-revive' .agents/skills/pfc-evening-checkin/SKILL.md \
     && echo "evening-checkin→pfc-revive:OK" \
     || echo "evening-checkin→pfc-revive:MISSING"
   grep -q 'revive_watchlist\.py' .agents/skills/pfc-review/SKILL.md \
     && echo "review→revive_watchlist.py:OK" \
     || echo "review→revive_watchlist.py:MISSING"
   grep -q 'pfc-evening-checkin' .agents/skills/pfc-review/SKILL.md \
     && echo "review→evening-checkin(gate delegation):OK" \
     || echo "review→evening-checkin(gate delegation):MISSING"
   grep -q 'pfc-revive' AGENTS.md \
     && echo "AGENTS.md→pfc-revive:OK" \
     || echo "AGENTS.md→pfc-revive:MISSING"
   ```

   Any `MISSING` / `PARSE-FAIL` / `RUN-FAIL` → 🔴 in the report. The script-run check (c) is the load-bearing one — a passing parse doesn't catch broken jq filters inside the script.

7. **Rolling-review wiring (three-way drift check):**

   Every review-ledger id needs a gate (or it can never surface), a map row (or a surfaced item has no next step), and a row in `/pfc-review`'s form table (or it cannot be done as a form). Every gate, map row and form row needs a ledger id (or it's dead code). Compare all four sets.

   ```bash
   CHK=.agents/skills/pfc-evening-checkin/SKILL.md

   # (a) ids in the ledger
   jq -r '.id' data/review-ledger.ndjson | sort -u > /tmp/ledger-ids

   # (b) ids with a `case` branch in the gate() block — one branch may list
   #     several ids separated by |, so split on that too.
   awk '/^gate\(\)/{f=1;next} f && /^\}/{f=0} f' "$CHK" \
     | grep -oE '^[[:space:]]*[a-z][a-z0-9|-]*\)' \
     | tr -d ' )' | tr '|' '\n' | sort -u > /tmp/gate-ids

   # (c) ids with a row in the owning-skill map (leading `| \`id\` |` cells)
   grep -oE '^\| `[a-z][a-z0-9-]*` \|' "$CHK" | tr -d '|` ' | sort -u > /tmp/map-ids

   echo "--- ledger ids with no gate (can never surface) ---"; comm -23 /tmp/ledger-ids /tmp/gate-ids
   echo "--- gate ids not in the ledger (dead code) ---";      comm -13 /tmp/ledger-ids /tmp/gate-ids
   echo "--- ledger ids with no map row (no next step) ---";   comm -23 /tmp/ledger-ids /tmp/map-ids
   echo "--- map rows not in the ledger (dead row) ---";       comm -13 /tmp/ledger-ids /tmp/map-ids

   # (d) ids with a row in /pfc-review's form table (same leading-cell shape; one
   #     row may list several ids separated by ", ")
   grep -E '^\| `[a-z][a-z0-9-]*`' .agents/skills/pfc-review/SKILL.md | cut -d'|' -f2 \
     | grep -oE '`[a-z][a-z0-9-]*`' | tr -d '`' | sort -u > /tmp/form-ids
   echo "--- ledger ids with no form row (no form to show) ---"; comm -23 /tmp/ledger-ids /tmp/form-ids
   echo "--- form rows not in the ledger (dead row) ---";          comm -13 /tmp/ledger-ids /tmp/form-ids
   ```

   Any non-empty list → 🟡, except "ledger ids with no gate," which is 🔴: that item silently never runs, and nothing else in the system notices. Fix by adding the missing branch/row, or by removing the ledger entry if the review is genuinely retired.

   `/pfc-review` runs the same ledger one review at a time, as a form. It owns the form table (rows, options, and what each answer writes) but deliberately **no** copy of the gate table or the owning-skill map: it re-reads both from the evening check-in each run. Confirm that delegation is intact and that no second gate has crept in:

   ```bash
   REV=.agents/skills/pfc-review/SKILL.md
   grep -q 'data/review-ledger\.ndjson' "$REV" && echo "review→ledger:OK" || echo "review→ledger:MISSING"
   grep -q 'pfc-evening-checkin' "$REV"       && echo "review→gate-source:OK" || echo "review→gate-source:MISSING"
   grep -qE '^gate\(\)' "$REV" \
     && echo "review:DUPLICATE-GATE (a second gate() definition will drift from Step 3c)" \
     || echo "review:no-duplicate-gate:OK"
   ```

7b. **Focus vehicles + habit ramps** (see [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md)):

   ```bash
   # (a) Every active non-consuming focus declares ≥1 vehicle habit, and every
   #     vehicle id resolves. This echoes the validator check on purpose — the
   #     validator guards the DATA, this guards against schema-side drift.
   DECLARED=$(awk '/^(daily|monthly)_habits:/{f=1;next} /^[a-z_]+:/{f=0} f && /^  - id:/{print $3}' \
     config/habit_schema.yaml | tr -d '"' | sort -u)
   jq -r 'select(.retired_date==null and .tier!="consuming" and ((.habits//[])|length)==0)
          | "focus_no_vehicle:\(.title)"' 4-focus/_data/focus.ndjson
   jq -r 'select(.retired_date==null) | .habits[]?' 4-focus/_data/focus.ndjson | sort -u \
     | comm -23 - <(echo "$DECLARED") | sed 's/^/focus_unknown_vehicle:/'

   # (b) Every ramp block satisfies starter <= frequency <= target.
   python3 - <<'PY_RAMP'
   import yaml
   s = yaml.safe_load(open("config/habit_schema.yaml"))
   for block in ("daily_habits", "monthly_habits"):
       for h in s.get(block) or []:
           r = h.get("ramp")
           if not r:
               continue
           if not (r["starter"] <= h["frequency"] <= r["target"]):
               print(f"ramp_out_of_band:{h['id']}:"
                     f"{r['starter']}<={h['frequency']}<={r['target']}")
   PY_RAMP

   # (c) The daily-habit cap agrees between the schema comment and the validator.
   #     grep -oE, not -oP: the macOS system grep has no -P and would report false drift.
   SCHEMA_CAP=$(grep -oE 'Daily habits: max [0-9]+' config/habit_schema.yaml | grep -oE '[0-9]+$')
   VALIDATOR_CAP=$(grep -oE 'daily_count" -gt [0-9]+' scripts/validate.sh | grep -oE '[0-9]+$')
   [ "$SCHEMA_CAP" = "$VALIDATOR_CAP" ] \
     && echo "habit_cap_agrees:$SCHEMA_CAP" \
     || echo "habit_cap_drift:schema=$SCHEMA_CAP validator=$VALIDATOR_CAP"
   ```

   `focus_no_vehicle` / `focus_unknown_vehicle` / `ramp_out_of_band` / `habit_cap_drift` → 🔴.

8. **TRMNL plumbing:**

   Also diff each pushed plugin's **server copy against the repo** when `TRMNL_API_KEY` is set (clone with `trmnl/bin/trmnlp clone srv-<name> <id>` into a temp dir and `diff` the `.liquid` files) — the repo is the only writer of markup, but a repo edit only reaches the device when someone remembers `trmnlp push`, and a stale server copy fails *silently*: every poll returns 200 while the screen renders empty loops. Any drifted view → re-push that plugin (`cd trmnl/<name> && echo y | ../bin/trmnlp push`), then `git restore trmnl/<name>/src/settings.yml` (the push round-trips the live bearer token into the file — never commit it). If `TRMNL_API_KEY` is absent, report the check as skipped rather than silently passing.

   ```bash
   # (a) Every plugin folder has the three required files
   for d in trmnl/*/; do
     n=$(basename "$d"); [ "$n" = "bin" ] && continue
     for f in .trmnlp.yml src/settings.yml src/full.liquid; do
       [ -f "$d$f" ] || echo "trmnl:$n:MISSING:$f"
     done
   done

   # (b) Folder set == BUILDERS key set
   ls -d trmnl/*/ | xargs -n1 basename | grep -v '^bin$' | sort -u > /tmp/trmnl-folders
   awk '/^BUILDERS = \{/{f=1;next} f && /^\}/{f=0} f' automations/scripts/trmnl_push.py \
     | grep -oE '"[a-z0-9-]+"' | tr -d '"' | sort -u > /tmp/trmnl-builders
   echo "--- folder with no builder (screen never updates) ---"; comm -23 /tmp/trmnl-folders /tmp/trmnl-builders
   echo "--- builder with no folder (dead code) ---";            comm -13 /tmp/trmnl-folders /tmp/trmnl-builders

   # (c) Every plugin listed in both doc tables
   while read -r p; do
     grep -qF "$p" docs/trmnl-plugins.md || echo "trmnl:$p:missing from docs/trmnl-plugins.md"
     grep -qF "$p" trmnl/README.md      || echo "trmnl:$p:missing from trmnl/README.md"
   done < /tmp/trmnl-folders

   # (d) Leaked bearer token guard. Match the KEY at line start — every settings.yml
   #     carries a comment explaining these are UI-only, so a bare substring grep
   #     false-positives on all of them.
   grep -lE '^polling_(url|headers):' trmnl/*/src/settings.yml 2>/dev/null \
     && echo "trmnl:POLLING-KEY-LEAK (a bearer token may be committed)" \
     || echo "trmnl:polling-keys:clean"

   # (e) Framework hard rules — these fail silently on the device, not at lint time
   grep -rnE 'style="|<style>|usetrmnl\.com' trmnl/*/src/*.liquid
   grep -rnP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' trmnl/*/src/*.liquid

   # (f) Build output must not be tracked
   git ls-files 'trmnl/*/_build/*' | head

   # (g) Design-system plugin still declared (dropping either key silently removes it)
   grep -q 'trmnl-agent-skills' .claude/settings.json && echo "trmnl:plugin-declared:OK" \
     || echo "trmnl:plugin-declared:MISSING"

   # (h) Endpoint transport wiring, only when a plugin actually polls
   if grep -qE '^\s*strategy:\s*polling' trmnl/*/src/settings.yml 2>/dev/null; then
     [ -f automations/scripts/trmnl_serve.py ] && echo "trmnl_serve.py:OK" || echo "trmnl_serve.py:MISSING"
     grep -q 'TRMNL_SERVE_TOKEN' .env.example && echo "TRMNL_SERVE_TOKEN:declared" || echo "TRMNL_SERVE_TOKEN:MISSING"
     for u in pfc-trmnl-serve.service pfc-repo-sync.service pfc-repo-sync.timer; do
       grep -qF "$u" automations/systemd/install.sh \
         && echo "units:OK:$u" \
         || echo "units:MISSING-FROM-UNITS-ARRAY:$u (the reconciler will tear it down on next install)"
     done
   fi

   # (i) Calendar cache (written by the two Calendar-fetching render paths, read by pfc-week)
   if [ -f data/calendar-cache.json ]; then
     jq -e '.fetched_at and .events' data/calendar-cache.json >/dev/null 2>&1 \
       && echo "calendar-cache:OK" || echo "calendar-cache:MALFORMED"
   fi
   ```

   A unit template under `automations/systemd/` that is absent from the `UNITS` array in `install.sh` is 🔴, not 🟡 — the reconcile pass at the top of `install.sh` stops, disables, and deletes any deployed `pfc-*` unit not in `UNITS`, so the next install silently tears down a service the docs tell users to rely on.

8b. **Web UI plumbing** (skip when `web/` is absent):

   ```bash
   # The twelve writer actions: web_write.py and the routes in web/src/pages/api/write/
   # agree on the same set. Two actions are CLI-only on purpose and have no route:
   # drop-pick (the reMarkable swap box) and review-seen (review_forms.py --finish).
   writer=$(grep -oE '"[a-z]+-[a-z]+": \((TASK_ID|HABIT_ID|FOCUS_ID|DAY|RATING_KEY|GROUND_ID|PROJECT_ID)' automations/scripts/web_write.py | cut -d'"' -f2 | grep -vxE 'drop-pick|review-seen' | sort -u)
   routes=$(ls web/src/pages/api/write | sed 's/\.ts$//' | sort -u)
   [ "$writer" = "$routes" ] && echo "web_write_actions:OK" || echo "web_write_actions:FAIL"

   # The writer's lock is ignored, and a dry run of an id that does not exist exits 2
   # with a JSON error and changes nothing.
   git check-ignore -q data/.web-write.lock && echo "web_write_lock_ignored:OK" || echo "web_write_lock_ignored:FAIL"
   before=$(git status --porcelain)
   out=$(python3 automations/scripts/web_write.py --dry-run complete-task task-00000000-000); code=$?
   { [ "$code" = 2 ] && echo "$out" | grep -q '"ok": false' && [ "$(git status --porcelain)" = "$before" ]; } \
     && echo "web_write_dry_run:OK" || echo "web_write_dry_run:FAIL"

   # Every ledger review has a form and a home-page pointer.
   python3 -m pytest -q automations/scripts/tests/test_review_forms.py automations/scripts/tests/test_web_write.py \
     automations/scripts/tests/test_home_data.py >/dev/null && echo "web_python_tests:OK" || echo "web_python_tests:FAIL"
   ```

9. **Report:**

   Output a table sorted by severity:

   | Severity | Domain | Issue | Location | Proposed fix |
   |---|---|---|---|---|
   | 🔴 | validator | … | … | … |
   | 🟡 | integrity | … | … | … |
   | 🟢 | docs | … | … | … |

   Then a numbered action list. Autonomously fix trivial drift (normalize enum typos, rewrite dead link paths, patch a stale field in a doc). For anything with judgment stakes (delete a file, merge skills, restructure docs), present the option and wait for the user.

10. **Commit** (if autonomous fixes were made):
   ```bash
   git add -A && git commit -m "system: repo maintenance [YYYY-MM-DD]" && git push
   ```
   If only reports were generated (no fixes), don't commit.

## What this skill is NOT

- **Not `/pfc-usage-audit`** — that skill asks "is the system being *used* and producing?" (logging gaps, data freshness, stale reviews, surfaces nobody reads). This skill asks "is the *machinery* intact?" (schemas, references, docs).
- **Not `/pfc-status`** — that's the life-content dashboard.
- **Not a content review** — no opinions on which tasks to keep, which habits to adopt, which projects to prioritize.

## Cadence

- **Required after** any moderate-to-large structural change — folder restructure, mass file move, schema change, new skill, doc rewrite, or any commit that touches >5 files. The agent must run this skill as the **final step before declaring the change done**, even if every reference appears updated. See AGENTS.md § "Run /pfc-repo-maintenance after every moderate-to-large structural change" for the trigger list.
- **Recommended before** such a change to baseline what's clean.
- **Monthly** as an idle-time baseline run.
- **On demand** any time the user asks ("repo maintenance", "audit the repo", "docs check").

## Removing an automation — teardown checklist

When tearing out a system automation (script + systemd unit + binary), the repo and the deployed VPS state drift independently. The Deprecated-vocabulary grep above catches lingering *repo* references; nothing in the repo can detect *VPS* drift. Run both passes — missing either leaves orphans.

**Repo pass:**
1. Delete the script(s) under `automations/scripts/`.
2. Delete the unit template(s) under `automations/systemd/`.
3. Remove the unit name(s) from the `UNITS` array in `automations/systemd/install.sh`.
4. Append a row to the Deprecated-vocabulary table above with date and reason.
5. Extend the deprecated-vocabulary grep at the bottom of that subsection so future audits flag stray references.
6. Commit (`system: tear out <name>`).

**VPS pass** — runs automatically on the next `install.sh` execution. The reconcile block at the top of `install.sh` stops, disables, and removes any `pfc-*.{service,timer}` in `~/.config/systemd/user/` that's no longer in `UNITS`. So: re-run `install.sh` after every teardown commit.

If immediate cleanup is needed (don't want to wait for next deploy):

```bash
# As the owning user — user-scoped systemd is per-user.
# Running as the wrong user returns empty results, not an error.
systemctl --user stop <unit>
systemctl --user disable <unit>
rm ~/.config/systemd/user/<unit>
systemctl --user daemon-reload
```

**Thorough VPS orphan sweep.** systemd is only one of several places an automation leaves things. The repo cannot track artifacts outside itself — walk this list on the deployed host any time you tear something out (and again periodically if the automation was long-lived). Run every check **as the owning user** — user-scoped state is per-user and returns silently empty when queried from the wrong account.

| Where | Check | Typical content |
|---|---|---|
| `~/.config/systemd/user/` | `ls ~/.config/systemd/user/ \| grep <keyword>` | Unit files (auto-reconciled by `install.sh` for `pfc-*`; check anyway) |
| `systemctl --user` | `systemctl --user list-units --type=service \| grep <keyword>` · `systemctl --user list-unit-files \| grep <keyword>` | Running + enabled units |
| `~/.local/bin/` | `ls ~/.local/bin/ \| grep <keyword>` · `which <name>` | Installed binaries |
| `~/.local/lib/` | `ls ~/.local/lib/ \| grep <keyword>` | Bundled libraries / jars |
| `~/.local/share/` | `ls ~/.local/share/ \| grep <keyword>` | Account / runtime data |
| `~/.config/` | `ls ~/.config/ \| grep <keyword>` | Per-app config dirs |
| `~/.cache/` | `ls ~/.cache/ \| grep <keyword>` | Caches, logs |
| User crontab | `crontab -l \| grep <keyword>` | Cron entries |
| Running processes | `ps -ef \| grep -i <keyword> \| grep -v grep` | Stragglers still alive |
| Recent journald | `journalctl --user -u <unit> -n 50 --no-pager` | Confirms the unit actually stopped |
| Repo-side `.env` | `grep -i <keyword> .env .env.example` | Unused env vars after teardown |
| Broad sweep | `find ~ -name '*<keyword>*' 2>/dev/null` | Anything missed by the targeted checks |

For each hit: stop/disable/remove using the tool that owns it (`systemctl --user`, `crontab -e`, `rm`), then re-run the sweep until it's clean.

**Scope note.** `<keyword>` should be the automation name *and* its underlying tool name. The first finds the third-party tool's footprint; the second finds the PFC-side wrapper.

**Why this matters.** A deployed systemd unit that survives a repo teardown can crash-loop under `Restart=on-failure` for days unnoticed. The reconcile block in `install.sh` fixes that for `pfc-*` units, but only catches systemd — every other artifact category needs the sweep table above. Every teardown needs a repo commit, an `install.sh` re-run, *and* a walk of the orphan sweep table.
