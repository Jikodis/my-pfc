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
| **Cross-file integrity** | task.project → projects.ndjson; task.depends_on → tasks.ndjson or tasks-archive.ndjson (no self-reference); daily-focus ids (`critical`, `bonus` and `skipped`) → tasks.ndjson or tasks-archive.ndjson; habit.area → `2-areas/`; project.area → `2-areas/`; insight.area → `2-areas/`; insight.graduated_to (when set) resolves to a real task/project/habit; finding.source_hypothesis_id → hypotheses.ndjson; finding.superseded_by → findings.ndjson; supplements.ndjson active `started` date not in the future; supplements.ndjson schema referenced in `docs/data-model.md`; insights.ndjson + insight_schema referenced in `docs/data-model.md`; habits-daily.ndjson: any record with `skipped:true` must have `completed:false` and a non-empty `skip_reason`; tasks.ndjson: any record with `deferred:true` must have `status:"open"` and a non-empty `deferred_reason` (a done task cannot be parked, and a park with no stated reason is unrecoverable at un-park time); focus.area → `2-areas/` and the pursuit cap ≤6 (both covered by validator §14 — reference it, don't re-implement); focus.link.ref (when set) resolves to a vision slug / habit id / project id; grounding.area (when set) → `2-areas/` |
| **Orphans** | Scripts called by no skill; skills referencing missing files/scripts; empty NDJSON files referenced in skills |
| **Stale** | tasks.ndjson > 200 lines; done tasks not archived; unpushed commits; docs untouched 90+ days; expected notes subdirectories (`notes/daily/`, `notes/yearly/`) exist (`notes/weekly/` + `notes/monthly/` are archival — the ritual weekly/monthly check-ins were replaced by the rolling-review ledger, so nothing writes there anymore and they are not required) |
| **Docs accuracy** | CLAUDE.md claims vs reality; every data/ file documented in `docs/data-model.md`; every skill listed exists; no contradictions between CLAUDE.md and `docs/`; `data/findings.ndjson` and `config/finding_schema.yaml` both present in `docs/data-model.md`; `data/supplements.ndjson` and `config/supplement_schema.yaml` both present in `docs/data-model.md`; `data/hypotheses.ndjson` and `config/hypothesis_schema.yaml` both present in `docs/data-model.md`; `4-focus/_data/focus.ndjson` + `config/focus_schema.yaml` + `config/focus.yaml` all present; `data/grounding.ndjson` + `config/grounding_schema.yaml` both present; `data/review-ledger.ndjson` + `config/review_ledger_schema.yaml` both present |
| **Docs coverage** | Every active skill has a trigger phrase; every cadence in `docs/cadences.md` maps to a skill; every config file has a doc reference |
| **Mirrored-list drift** | Lists in `docs/` that are mirrored from CLAUDE.md (commit conventions, auto-commit, ask-before-commit) match verbatim |
| **Bare-path references** | Unlinked path mentions in prose (e.g. `notes/`, `data/foo.ndjson`) resolve to real files/directories |
| **Tool-usage contradictions** | No doc recommends a tool that CLAUDE.md forbids (e.g. `sed`/`echo >>` on NDJSON) |
| **Deprecated vocabulary** | No doc still references deleted files or removed concepts |
| **Env-var coverage** | Every var declared in `.env.example` is referenced by at least one script or skill; vars referenced in scripts/skills exist in `.env.example`. `.env` populating is informational only — never a failure. |
| **pfc-revive plumbing** | `data/revive-events.ndjson` exists and parses (validator §13); `config/revive_event_schema.yaml` exists; `automations/scripts/revive_watchlist.py` exists and runs cleanly against the live repo; integration references intact — `pfc-review` SKILL.md cites `revive_watchlist.py` (Step 1 gate) and `pfc-revive` (owning-skill map), AGENTS.md mentions `pfc-revive` |
| **Rolling-review wiring** | Every id in `data/review-ledger.ndjson` has BOTH a `case` branch in the `gate()` block of `pfc-review` Step 1 AND a row in that skill's owning-skill map, and `REVIEW_SKILLS` in `automations/scripts/home_data.py` (the tour's one-due-review button) carries the same ids — and none of the three names an id the ledger doesn't have. A ledger id with no gate never surfaces in a catch-up, a gate with no ledger id is dead code, a surfaced id with no map row leaves the user with no next step |
| **Current Focus plumbing** | `4-focus/_data/focus.ndjson` parses (validator §14); `config/focus_schema.yaml` + `config/focus.yaml` exist; the pursuit cap in `config/focus.yaml` matches the cap the validator and `automations/scripts/trello_render.py` enforce; `4-focus/README.md` + `4-focus/AGENTS.md` + `4-focus/CLAUDE.md` all present |
| **Front-of-Mind plumbing** | `data/grounding.ndjson` parses (validator §16); `config/grounding_schema.yaml` exists; the `soft_cap.active_records` value in the schema matches `GROUNDING_CAP` in `automations/scripts/trello_render.py` |
| **TRMNL plumbing** | Every folder under `trmnl/` (except `bin/`) has `.trmnlp.yml` + `src/settings.yml` + `src/full.liquid`; every plugin folder has a matching key in `BUILDERS` in `automations/scripts/trmnl_push.py` and vice versa (a folder with no builder never updates its screen; a builder with no folder is dead code); every plugin appears in the tables in `docs/trmnl-plugins.md` and `trmnl/README.md`; no `_build/` output is tracked by git; no `polling_url:` / `polling_headers:` **key** appears in any `src/settings.yml` (the header carries a bearer token and `trmnlp push` would round-trip it into the repo); `TRMNL_SERVE_TOKEN` is declared in `.env.example`; `.claude/settings.json` still declares the `trmnl` plugin under both `extraKnownMarketplaces` and `enabledPlugins`; framework hard rules hold in `trmnl/**/*.liquid` (no `style="`, no `<style>`, no emoji, no `usetrmnl.com` URLs); `data/calendar-cache.json` (when present) parses and has `fetched_at` + `events`; the TRMNL tests under `automations/scripts/tests/` pass (`test_trmnl_home.py` included); `BUILDERS` lists one plugin per band of the web home page, in the page's order (a band added to or removed from `web/src/pages/index.astro` needs the same change here) |
| **Web UI plumbing** | Every NDJSON data file is in `HOME_DATA` or `AGENT_ONLY_DATA` in `web/src/lib/data-files.ts`: `cd web && npx vitest run test/data-files.test.ts` (a failure lists the files in neither list); the web writer has the twelve actions that `web/src/components/ActionButton.astro`, `web/src/pages/api/write/` and `web/AGENTS.md` name; `web/AGENTS.md` exists and `web/CLAUDE.md` is exactly the one line `@AGENTS.md`; `data/.web-write.lock` is git-ignored, `web_write.py --dry-run` on a missing id exits 2 without changing `git status`, and the writer tests pass; `scripts/open-web-ui.sh` is executable, on the allow list, and still run by `pfc-daily-summary` |
| **Area note indexes** | For every `2-areas/<area>/CLAUDE.md` that exists, the rows in its Contents table match the `.md` files actually in that folder (excluding `statement.md` and `CLAUDE.md` itself). Area folders ship without a `CLAUDE.md` — an absent index is not a finding, a stale one is |

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
   jq -r '.critical[]?, (.bonus // empty), .skipped[]?' 6-tasks/_data/daily-focus.ndjson | sort -u > /tmp/focus-ids
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
   # Bash permission hook registered in .claude/settings.json, and its tests pass
   jq -e '.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[] | select(.command | endswith("scripts/hook-allow-known-commands.py"))' .claude/settings.json >/dev/null \
     && echo "hook:OK:allow-known-commands registered" || echo "hook:MISSING:allow-known-commands (PreToolUse Bash entry in .claude/settings.json)"
   pytest scripts/tests -q >/dev/null 2>&1 \
     && echo "hook:OK:allow-known-commands tests" || echo "hook:FAIL:allow-known-commands tests (run pytest scripts/tests -q)"
   # Session sync hook registered — levels the clone with origin at session start, so the
   # clones (a laptop and a server, say) stop stranding commits on each other (see automations/scripts/repo_sync.py)
   jq -e '.hooks.SessionStart[]? | .hooks[] | select(.command | endswith("scripts/hook-session-sync.sh"))' .claude/settings.json >/dev/null \
     && echo "hook:OK:session-sync registered" || echo "hook:MISSING:session-sync (SessionStart entry in .claude/settings.json)"
   [ -x scripts/hook-session-sync.sh ] && echo "hook:OK:session-sync executable" || echo "hook:MISSING:session-sync script not executable"
   pytest automations/scripts/tests/test_repo_sync.py -q >/dev/null 2>&1 \
     && echo "hook:OK:repo_sync tests" || echo "hook:FAIL:repo_sync tests (run pytest automations/scripts/tests/test_repo_sync.py -q)"
   # Missed check-in hook registered — flags yesterday or the day before when either was never rated
   jq -e '.hooks.SessionStart[]? | .hooks[] | select(.command | endswith("scripts/hook-missing-checkin.sh"))' .claude/settings.json >/dev/null \
     && echo "hook:OK:missing-checkin registered" || echo "hook:MISSING:missing-checkin (SessionStart entry in .claude/settings.json)"
   [ -x scripts/hook-missing-checkin.sh ] && echo "hook:OK:missing-checkin executable" || echo "hook:MISSING:missing-checkin script not executable"
   # Daily sync job present (docs/install/daily-sync.md)
   [ -x scripts/daily-sync.sh ] && echo "daily-sync:OK" || echo "daily-sync:MISSING-OR-NOT-EXECUTABLE"
   ```

5. **Docs gardening:**
   - **CLAUDE.md accuracy**: for each skill listed, confirm it exists; for each file path mentioned, confirm it exists; for each rule (e.g. the active-project backstop, the Current Focus pursuit cap), confirm docs and schemas agree.
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
   - **Contradictions**: grep both CLAUDE.md and `docs/` for the same key facts (max projects, id formats, field names). Report any mismatches.
   - **Dead links**: grep all `.md` for `](./...)` or `](../...)` paths and verify each resolves.

   - **Area note indexes**: area folders ship without a `CLAUDE.md` and gain one lazily when the first note lands (see `2-areas/AGENTS.md`). Where one exists, its Contents table must list exactly the note files in that folder. A missing index is not a finding; a stale one is.
     ```bash
     for idx in 2-areas/*/CLAUDE.md; do
       [ -f "$idx" ] || continue
       dir=$(dirname "$idx")
       ls "$dir"/*.md 2>/dev/null | xargs -n1 basename \
         | grep -vE '^(statement|CLAUDE)\.md$' | sort -u > /tmp/area-files
       grep -oE '`[A-Za-z0-9_-]+\.md`' "$idx" | tr -d '`' | sort -u > /tmp/area-rows
       echo "--- $dir: files with no index row ---"; comm -23 /tmp/area-files /tmp/area-rows
       echo "--- $dir: index rows with no file ---"; comm -13 /tmp/area-files /tmp/area-rows
     done
     ```

   - **Mirrored-list drift** — CLAUDE.md is canonical; secondary docs that mirror its lists must match verbatim. Known mirrors:

     | CLAUDE.md section | Mirror location |
     |---|---|
     | "Auto-commit" bullets under Commit policy | `docs/automation-policy.md` "Auto-commit operations" |
     | "Ask before committing" bullets | `docs/automation-policy.md` "Ask-before-commit operations" |
     | "Commit message conventions" bullets | `docs/conventions.md` "Commit messages" |

     For each pair, extract the bulleted lines from both files and diff. The `awk '/start/,/end/'` range form does NOT work here — when the start pattern's prefix (e.g. `^### `) also matches the start line, the range opens and closes on the same line and returns nothing. Use a flag-toggle pattern instead:
     ```bash
     # Compare auto-commit lists (CLAUDE.md is canonical via AGENTS.md import)
     awk '/^### Auto-commit \(no confirmation needed\)$/{f=1;next} /^### /{f=0} f' AGENTS.md \
       | grep -E '^- ' | sort > /tmp/claude.txt
     awk '/^## Auto-commit operations \(no confirmation needed\)$/{f=1;next} /^## /{f=0} f' \
       docs/automation-policy.md | grep -E '^- ' | sort > /tmp/mirror.txt
     diff /tmp/claude.txt /tmp/mirror.txt
     ```
     Any asymmetric diff → update the mirror (AGENTS.md is canonical).

   - **Bare-path verification** — unlinked path references in prose should resolve. Grep the live docs:
     ```bash
     grep -rnE '\b(data|config|0-me|1-values|2-areas|3-visions|4-focus|5-projects|6-tasks|7-habits|notes|trmnl|automations)/[A-Za-z0-9_.-]+' \
       --include='*.md' \
       CLAUDE.md AGENTS.md README.md docs/ 0-me/ 1-values/ 2-areas/AGENTS.md trmnl/AGENTS.md \
       4-focus/AGENTS.md 5-projects/AGENTS.md 6-tasks/AGENTS.md 7-habits/AGENTS.md data/AGENTS.md \
       | grep -oE '\b(data|config|0-me|1-values|2-areas|3-visions|4-focus|5-projects|6-tasks|7-habits|notes|trmnl|automations)/[A-Za-z0-9_./-]+' \
       | grep -vE 'YYYY|MM|NN|/\.[a-z_]+\.tmp$|XX|<area>|<slug>|<plugin>|<area-folder-name>' \
       | sort -u
     ```
     Keep the folder alternation in **both** `grep` expressions in sync with the live top-level layout (`4-focus/` is easy to forget — it was the last numbered folder added). A folder missing from the alternation means every bare path under it goes unchecked.
     For each path extracted, `test -e` to confirm it exists. Report misses. The `grep -vE` filter drops template placeholders (`YYYY-MM-DD`, `WNN`, `<slug>`) and jq tempfile names (`data/.jq_update.tmp`) — these are *intentional* non-existent paths in conventions and code examples, not drift.

   - **Tool-usage contradictions** — CLAUDE.md forbids certain tools on structured data. Grep secondary docs for the forbidden forms:
     ```bash
     grep -rnE 'via sed|sed.*ndjson|echo.*>>.*\.ndjson|sed -i.*ndjson' \
       --include='*.md' docs/ CLAUDE.md AGENTS.md 0-me/ 1-values/ README.md trmnl/AGENTS.md \
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
     | `pfc-morning-checkin` | — | Deleted. There is no morning ritual. |
     | `pfc-weekly-checkin` | the rolling-review ledger + `/pfc-review` | Deleted. Weekly review work became rolling-ledger items. |
     | `pfc-monthly-checkin` | the rolling-review ledger + `/pfc-review` | Deleted. Same ledger; monthly-cadence items. |
     | `📧 Email Priorities` (Trello list) | email→task pipeline | Replaced. Labeled inbox emails auto-create tasks via `pfc-email-triage` Step 0; there is no rendered email list. |
     | `passion-brainstorm` | `3-visions/_data/vision-brainstorm.ndjson` + `/pfc-vision-brainstorm` | Renamed. The markdown file is gone; the exercise is a skill writing NDJSON. |
     | `daily_pulse` (module) | `pulse` (`automations/scripts/pulse.py`) | Renamed. Any `import daily_pulse` / `from daily_pulse` is dead. |
     | ✅ calendar completion-sync | Trello Mark Complete + `/pfc-sync-trello` | Retired. Focus completion is never inferred from a calendar-event title marker. |
     | `4-focus` living in `data/focus.ndjson` | `4-focus/_data/focus.ndjson` | Moved when the Focus layer got its own numbered folder. |
     | `pfc-learned` (TRMNL plugin + builder) | — | Deleted — surfaced too much; insights/findings review lives in the rolling-review ledger. |
     | `pfc-slipping` (TRMNL plugin + builder) | — | Reworked into `pfc-back-on-track`, which is itself deleted (below). |
     | `life_event` field (day-tracking) | — | Deleted. Days are never tagged or dropped for what happened in them. |
     | `pfc-system-health` (skill) + ledger id `system-health` | `pfc-usage-audit` / `usage-audit` | Renamed — the description now says what it audits (usage, not machinery). |
     | `pfc-evening-checkin` (skill) | the web home page tour (`Walk me through`), the daily sync job (`scripts/daily-sync.sh`), and `/pfc-review` | Deleted. The tour is the any-time daily spine; the daily sync job runs the Trello and email syncs; `/pfc-review` now owns the gate table and the owning-skill map. |
     | 2+1 calendar anchor (`PFC - 🎯 2+1` recurring event) | the tour's picks step | Deleted. The 2+1 lives on the web page, not the calendar. |
     | `pfc-compass`, `pfc-back-on-track`, `pfc-pulse-trend` (TRMNL plugins + builders) | `pfc-values`, `pfc-visions`, and the other band screens (`automations/scripts/trmnl_home.py`) | Deleted. The TRMNL screens now mirror the web home page band for band. |
     | `6-actions/` folder, the `VAVFPAH` acronym, the `✅ Actions` Trello list | `6-tasks/`, `VAVFPTH`, `✅ Tasks` | Renamed. The Actions layer is now called Tasks. |

     ```bash
     grep -rnE 'pfc-morning-checkin|pfc-weekly-checkin|pfc-monthly-checkin|Email Priorities|render_email|--email-data|passion-brainstorm|daily_pulse|\bdata/focus\.ndjson|pfc-learned|build_pfc_learned|pfc-slipping|build_pfc_slipping|pfc-system-health|pfc-evening-checkin|pfc-compass|build_pfc_compass|pfc-back-on-track|build_pfc_back_on_track|pfc-pulse-trend|build_pfc_pulse_trend|6-actions/|VAVFPAH|✅ Actions' \
       --include='*.md' --include='*.py' \
       CLAUDE.md AGENTS.md README.md docs/ 0-me/ 1-values/ 2-areas/ 3-visions/ trmnl/ \
       .agents/skills/ automations/scripts/ \
       4-focus/AGENTS.md 5-projects/AGENTS.md 6-tasks/AGENTS.md 7-habits/AGENTS.md data/AGENTS.md
     ```

     The `\b` before `data/focus.ndjson` is required — without it the pattern also matches inside `4-focus/_data/focus.ndjson` and every correct path reads as a hit.

     Expected exceptions: this skill file itself contains the table and the grep — that's the registry, not drift. `AGENTS.md` carries one deliberate mention of "Email Priorities" in the sentence explaining that the list no longer exists; a mention *about* the removal should stay. The `pfc-usage-audit` skill's one "renamed from `pfc-system-health`" line is likewise a mention about the rename.

     Expected exceptions: this skill file itself contains the deprecated-vocabulary table and the grep — those are the registry, not drift.

     `life_event` is deliberately **not** in the grep. Surviving mentions (in `pfc-log-day`, `pfc-analyze-trends`, `docs/data-model.md`) are load-bearing "do NOT tag or discount days for external events" guardrails, not drift — the rule has to stay stated or the behavior creeps back. What the audit should catch instead is *reintroduction*: `jq -e 'has("life_event")' data/day-tracking.ndjson` must find nothing.

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

   Verify the revive-watchlist machinery is intact end-to-end. (Invariant: Signals C/D
   in `revive_watchlist.py` skip project-linked tasks — only standalone tasks age-flag;
   project health rides on signals A/B/F. See `6-tasks/AGENTS.md` § "Project tasks live
   outside the 2+1".)

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

   # (d) Integration references intact
   grep -q 'revive_watchlist\.py' .agents/skills/pfc-review/SKILL.md \
     && echo "review→revive_watchlist.py:OK" \
     || echo "review→revive_watchlist.py:MISSING"
   grep -q 'pfc-revive' .agents/skills/pfc-review/SKILL.md \
     && echo "review→pfc-revive:OK" \
     || echo "review→pfc-revive:MISSING"
   grep -q 'pfc-revive' AGENTS.md \
     && echo "AGENTS.md→pfc-revive:OK" \
     || echo "AGENTS.md→pfc-revive:MISSING"
   ```

   Any `MISSING` / `PARSE-FAIL` / `RUN-FAIL` → 🔴 in the report. The script-run check (c) is the load-bearing one — a passing parse doesn't catch broken jq filters inside the script.

7. **Rolling-review wiring (drift check):**

   Every review-ledger id needs a gate (or it can never surface in a catch-up), a row in the owning-skill map (or a surfaced item has no next step), and an entry in `REVIEW_SKILLS` (or the tour's one-due-review button has no skill to name). Every gate, map row, and `REVIEW_SKILLS` key needs a ledger id (or it's dead code). `pfc-review` is the one home of the gate table and the map; compare all four sets.

   ```bash
   REV=.agents/skills/pfc-review/SKILL.md

   # (a) ids in the ledger
   jq -r '.id' data/review-ledger.ndjson | sort -u > /tmp/ledger-ids

   # (b) ids with a `case` branch in the gate() block — one branch may list
   #     several ids separated by |, so split on that too.
   awk '/^gate\(\)/{f=1;next} f && /^\}/{f=0} f' "$REV" \
     | grep -oE '^[[:space:]]*[a-z][a-z0-9|-]*\)' \
     | tr -d ' )' | tr '|' '\n' | sort -u > /tmp/gate-ids

   # (c) ids with a row in the owning-skill map (leading `| \`id\` |` cells)
   grep -oE '^\| `[a-z][a-z0-9-]*` \|' "$REV" | tr -d '|` ' | sort -u > /tmp/map-ids

   # (d) keys of REVIEW_SKILLS in home_data.py (the tour's button)
   python3 -c "import sys; sys.path.insert(0, 'automations/scripts'); import home_data; print('\n'.join(sorted(home_data.REVIEW_SKILLS)))" > /tmp/home-ids

   echo "--- ledger ids with no gate (can never surface) ---"; comm -23 /tmp/ledger-ids /tmp/gate-ids
   echo "--- gate ids not in the ledger (dead code) ---";      comm -13 /tmp/ledger-ids /tmp/gate-ids
   echo "--- ledger ids with no map row (no next step) ---";   comm -23 /tmp/ledger-ids /tmp/map-ids
   echo "--- map rows not in the ledger (dead row) ---";       comm -13 /tmp/ledger-ids /tmp/map-ids
   echo "--- ledger ids missing from REVIEW_SKILLS ---";       comm -23 /tmp/ledger-ids /tmp/home-ids
   echo "--- REVIEW_SKILLS keys not in the ledger ---";        comm -13 /tmp/ledger-ids /tmp/home-ids
   ```

   Any non-empty list → 🟡, except "ledger ids with no gate," which is 🔴: that item silently never runs in a catch-up, and nothing else in the system notices. Fix by adding the missing branch, row, or key, or by removing the ledger entry if the review is genuinely retired. Change the map in `pfc-review` and `REVIEW_SKILLS` together.

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

8b. **Web UI plumbing:**

   The web UI is one page (`/`) plus Tasks (`/tasks`). Every NDJSON file in the repo is
   either read for the home page (`HOME_DATA`) or kept for the agent alone
   (`AGENT_ONLY_DATA`, which holds findings, hypotheses and insights), both in
   `web/src/lib/data-files.ts`. A new data file must be placed in one of them on purpose,
   so the guard is a test rather than an eye. There is no page-per-view check: the smoke
   script checks `/` and `/tasks`, and that the deleted pages answer 404.

   ```bash
   # (a) Every NDJSON data file is on the home page or agent-only. The test reads
   #     the live data folders, so it fails on a real new file, not on a fixture.
   (cd web && npx vitest run test/data-files.test.ts) \
     && echo "web_data_files_cover:OK" || echo "web_data_files_cover:FAIL"

   # (b) The subtree harness files are present and the shim is the one-line import.
   [ -f web/AGENTS.md ] && echo "web/AGENTS.md:OK" || echo "web/AGENTS.md:MISSING"
   [ "$(cat web/CLAUDE.md 2>/dev/null)" = "@AGENTS.md" ] \
     && echo "web/CLAUDE.md:OK" || echo "web/CLAUDE.md:NOT-A-SHIM"

   # (b2) The page is opened for the user, not left to be remembered: the opener script
   #      is executable, on the allow list, and still the last step of the daily summary.
   [ -x scripts/open-web-ui.sh ] && echo "open-web-ui.sh:OK" || echo "open-web-ui.sh:MISSING-OR-NOT-EXECUTABLE"
   grep -q '"Bash(scripts/open-web-ui.sh)"' .claude/settings.json \
     && echo "open-web-ui allow rule:OK" || echo "open-web-ui allow rule:MISSING"
   for skill in pfc-daily-summary; do
     grep -q 'scripts/open-web-ui.sh' ".agents/skills/$skill/SKILL.md" \
       && echo "$skill opens the web UI:OK" || echo "$skill opens the web UI:MISSING"
   done

   # (c) Every skill the chat panel names still exists: the ones page buttons start
   #     (slash commands in prompts.ts and any data-chat-prompt in a page), the ones
   #     skills.ts lists in TAKES_ARGS and PREFILL, and the drawer's pinned list in
   #     pinned.ts. A renamed skill otherwise leaves a button that sends a command
   #     nobody answers.
   { grep -rhoE "/pfc-[a-z0-9-]+" web/src/lib/chat/prompts.ts; \
     grep -rhoE "data-chat-prompt=[\"'{][^>]*" web/src/pages web/src/components | grep -oE "/pfc-[a-z0-9-]+"; \
     grep -oE "^  'pfc-[a-z0-9-]+':" web/src/lib/chat/skills.ts | tr -d " ':" | sed 's#^#/#'; \
     grep -oE "'pfc-[a-z0-9-]+'" web/src/lib/chat/pinned.ts | tr -d "'" | sed 's#^#/#'; } \
     | sort -u | while read -r cmd; do
       name="${cmd#/}"
       [ -f ".agents/skills/$name/SKILL.md" ] && echo "chat_skill $name:OK" || echo "chat_skill $name:MISSING"
     done

   # (c2) The twelve writer actions: web_write.py, the routes in web/src/pages/api/write/,
   #      and the ActionButton header agree on the same set.
   writer=$(grep -oE '"[a-z]+-[a-z]+": \((TASK_ID|HABIT_ID|FOCUS_ID|DAY|RATING_KEY|GROUND_ID|PROJECT_ID)' automations/scripts/web_write.py | cut -d'"' -f2 | sort -u)
   routes=$(ls web/src/pages/api/write | sed 's/\.ts$//' | sort -u)
   [ "$writer" = "$routes" ] && [ "$(echo "$writer" | wc -l | tr -d ' ')" = 12 ] \
     && echo "web_write_actions:12 OK" || echo "web_write_actions:FAIL"
   for a in $writer; do grep -q "$a" web/src/components/ActionButton.astro || echo "ActionButton header missing $a:FAIL"; done

   # (d) The web writer: its lock file is ignored, a dry run of an id that does not
   #     exist exits 2 with a JSON error and changes nothing, and its tests pass.
   git check-ignore -q data/.web-write.lock && echo "web_write_lock_ignored:OK" || echo "web_write_lock_ignored:FAIL"
   before=$(git status --porcelain)
   out=$(python3 automations/scripts/web_write.py --dry-run complete-task task-00000000-000); code=$?
   { [ "$code" = 2 ] && echo "$out" | grep -q '"ok": false' && [ "$(git status --porcelain)" = "$before" ]; } \
     && echo "web_write_dry_run:OK" || echo "web_write_dry_run:FAIL"
   python3 -m pytest -q automations/scripts/tests/test_web_write.py automations/scripts/tests/test_pfc_writes.py \
     && echo "web_write_tests:OK" || echo "web_write_tests:FAIL"
   ```

   Any `FAIL` / `MISSING` / `NOT-A-SHIM` → 🔴. A `chat_skill ...:MISSING` names a skill
   that was renamed or removed: update the template in `web/src/lib/chat/prompts.ts`, the
   page's `data-chat-prompt`, the `TAKES_ARGS` or `PREFILL` entry in `web/src/lib/chat/skills.ts`,
   or the name in `PINNED` in `web/src/lib/chat/pinned.ts`.
   `web/test/chat-prompts.test.ts` checks the prompts half of this on every test run. A failing (a) prints the uncovered file
   paths: add each one to `HOME_DATA` when `home_data.py` reads it for the home page, or to
   `AGENT_ONLY_DATA` when only the agent uses it, both in `web/src/lib/data-files.ts`.

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

- **Required after** any moderate-to-large structural change — folder restructure, mass file move, schema change, new skill, doc rewrite, or any commit that touches >5 files. The agent must run this skill as the **final step before declaring the change done**, even if every reference appears updated. See CLAUDE.md § "Run /pfc-repo-maintenance after every moderate-to-large structural change" for the trigger list.
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
