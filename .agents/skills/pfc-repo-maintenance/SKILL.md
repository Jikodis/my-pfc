---
name: pfc-repo-maintenance
description: Audit the repo's plumbing and documentation for drift, gaps, or broken references — not life content. Use when the user says "repo maintenance", "maintenance check", "repo audit", "docs audit", "clean the repo", "docs check", or before a structural change. This is NOT /pfc-system-health (life-data completeness) and NOT /pfc-status (content view).
---

# Repo Maintenance

Verify the machinery and docs are clean, accurate, and coherent. Fix trivial drift autonomously; surface judgment calls to the user.

## Scope

| Domain | Checked |
|---|---|
| **Validation** | `scripts/validate.sh` (NDJSON parse, schema lint, skill frontmatter) |
| **Cross-file integrity** | task.project → projects.ndjson; task.depends_on → tasks.ndjson or tasks-archive.ndjson (no self-reference); daily-focus ids → tasks.ndjson; habit.area → `2-areas/`; project.area → `2-areas/`; insight.area → `2-areas/`; insight.graduated_to (when set) resolves to a real task/project/habit; finding.source_hypothesis_id → hypotheses.ndjson; finding.superseded_by → findings.ndjson; supplements.ndjson active `started` date not in the future; supplements.ndjson schema referenced in `docs/data-model.md`; insights.ndjson + insight_schema referenced in `docs/data-model.md`; habits-daily.ndjson: any record with `skipped:true` must have `completed:false` and a non-empty `skip_reason` |
| **Orphans** | Scripts called by no skill; skills referencing missing files/scripts; empty NDJSON files referenced in skills |
| **Stale** | tasks.ndjson > 200 lines; done tasks not archived; unpushed commits; docs untouched 90+ days; expected notes subdirectories (`notes/daily/`, `notes/weekly/`, `notes/monthly/`, `notes/yearly/`) exist |
| **Docs accuracy** | CLAUDE.md claims vs reality; every data/ file documented in `docs/data-model.md`; every skill listed exists; no contradictions between CLAUDE.md and `docs/`; `data/findings.ndjson` and `config/finding_schema.yaml` both present in `docs/data-model.md`; `data/supplements.ndjson` and `config/supplement_schema.yaml` both present in `docs/data-model.md`; `data/hypotheses.ndjson` and `config/hypothesis_schema.yaml` both present in `docs/data-model.md` |
| **Docs coverage** | Every active skill has a trigger phrase; every cadence in `docs/cadences.md` maps to a skill; every config file has a doc reference |
| **Mirrored-list drift** | Lists in `docs/` that are mirrored from CLAUDE.md (commit conventions, auto-commit, ask-before-commit) match verbatim |
| **Bare-path references** | Unlinked path mentions in prose (e.g. `notes/`, `data/foo.ndjson`) resolve to real files/directories |
| **Tool-usage contradictions** | No doc recommends a tool that CLAUDE.md forbids (e.g. `sed`/`echo >>` on NDJSON) |
| **Deprecated vocabulary** | No doc still references deleted files or removed concepts |
| **Env-var coverage** | Every var declared in `.env.example` is referenced by at least one script or skill; vars referenced in scripts/skills exist in `.env.example`. `.env` populating is informational only — never a failure. |
| **pfc-revive plumbing** | `data/revive-events.ndjson` exists and parses (validator §13); `config/revive_event_schema.yaml` exists; `automations/scripts/revive_watchlist.py` exists and runs cleanly against the live repo; integration references intact — `pfc-morning-checkin` SKILL.md cites `revive_watchlist.py`, `pfc-weekly-checkin` SKILL.md cites `pfc-revive`, AGENTS.md mentions `pfc-revive` |

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
     <(jq -r 'select(.project != "none" and .project != null) | .project' 5-actions/_data/tasks.ndjson | sort -u) \
     <(jq -r '.id' 4-projects/_data/projects.ndjson | sort -u)

   # Daily-focus task ids that don't exist in tasks.ndjson (live or archive)
   jq -r '.critical[]?, .bonus // empty' 5-actions/_data/daily-focus.ndjson | sort -u > /tmp/focus-ids
   jq -r '.id' 5-actions/_data/tasks.ndjson 5-actions/_data/tasks-archive.ndjson | sort -u > /tmp/task-ids
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
   jq -c 'select(.skipped == true and (.completed != false or (.skip_reason // "") == ""))' \
     6-habits/_data/habits-daily.ndjson

   # Insights → graduated_to: must resolve to a real task, project, or habit
   if [ -s data/insights.ndjson ]; then
     jq -r 'select(.status == "graduated") | .graduated_to' data/insights.ndjson | sort -u | while read -r tid; do
       [ -z "$tid" ] && continue
       case "$tid" in
         task-*) jq -e --arg t "$tid" 'select(.id == $t)' 5-actions/_data/tasks.ndjson 5-actions/_data/tasks-archive.ndjson >/dev/null 2>&1 || echo "insight graduated_to unresolved task: $tid" ;;
         proj-*) jq -e --arg t "$tid" 'select(.id == $t)' 4-projects/_data/projects.ndjson >/dev/null 2>&1 || echo "insight graduated_to unresolved project: $tid" ;;
         *)      grep -qE "^[[:space:]]*-[[:space:]]*id:[[:space:]]*[\"']?$tid[\"']?" config/habit_schema.yaml || echo "insight graduated_to unresolved habit_id: $tid" ;;
       esac
     done
   fi
   ```
   For each broken reference, report: file, id, what's missing. Ask before deleting.

3. **Orphan detection:**
   - For each `automations/scripts/*.py` and `automations/scripts/*.sh`: grep `.agents/skills/*/SKILL.md`, `automations/**/README.md`, and `automations/scripts/*` (for cross-imports) for the filename. Unreferenced scripts are orphans. **Exclude:** anything under `automations/scripts/tests/` (test files are expected to not be skill-referenced).
   - For each file path mentioned in a skill (`data/*.ndjson`, `config/*.yaml`, `automations/scripts/*`): verify the file exists. Skip placeholder example paths in this skill itself (e.g. `data/foo.ndjson` mentioned in the table of contents).
   - For each NDJSON file in `data/`: if it's empty AND not written by any skill, flag for deletion.

4. **Stale detection:**
   ```bash
   test $(wc -l < 5-actions/_data/tasks.ndjson) -gt 200 && echo "tasks.ndjson over 200 lines — run archive"
   jq -c 'select(.status == "done")' 5-actions/_data/tasks.ndjson | wc -l  # done tasks still in live file
   git log origin/main..HEAD --oneline                          # unpushed commits
   find docs -name '*.md' -mtime +90                            # docs older than 90 days
   # Notes subdirectory structure — all four must exist
   for d in notes/daily notes/weekly notes/monthly notes/yearly; do
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
   ```

5. **Docs gardening:**
   - **CLAUDE.md accuracy**: for each skill listed, confirm it exists; for each file path mentioned, confirm it exists; for each rule (e.g. "max 3 projects"), confirm docs and schemas agree.
   - **docs/data-model.md coverage**: every file in `data/*.ndjson` must appear in the doc. Every field used in the actual records must appear in the doc (use `jq -s 'map(keys)|flatten|unique'` per file to find gaps). For `config/`, every committed file must appear; **skip gitignored files** (use `git check-ignore` to filter — auth artifacts like `google_health_tokens.json` are local-only).
   - **Skill coverage**: every `.agents/skills/*/` must have `SKILL.md` with frontmatter matching directory name (validator already checks); every cadence named in `docs/cadences.md` should have a skill or explicit automation.
   - **Contradictions**: grep both CLAUDE.md and `docs/` for the same key facts (max projects, id formats, field names). Report any mismatches.
   - **Dead links**: grep all `.md` for `](./...)` or `](../...)` paths and verify each resolves.

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

   - **Bare-path verification** — unlinked path references in prose should resolve. Grep the live docs (exclude `docs/superpowers/` — historical):
     ```bash
     # -rnE (no -h): keep filenames so the superpowers/ filter actually fires.
     grep -rnE '\b(data|config|0-me|1-values|2-areas|3-visions|4-projects|5-actions|6-habits|notes|goals|automations)/[A-Za-z0-9_.-]+' \
       --include='*.md' \
       CLAUDE.md AGENTS.md README.md docs/ 0-me/ 1-values/ \
       4-projects/AGENTS.md 5-actions/AGENTS.md 6-habits/AGENTS.md data/AGENTS.md \
       | grep -vE '^docs/superpowers/' \
       | grep -oE '\b(data|config|0-me|1-values|2-areas|3-visions|4-projects|5-actions|6-habits|notes|goals|automations)/[A-Za-z0-9_./-]+' \
       | grep -vE 'YYYY|MM|NN|/\.[a-z_]+\.tmp$|XX|<area>|<slug>|<area-folder-name>' \
       | sort -u
     ```
     For each path extracted, `test -e` to confirm it exists. Report misses. The `grep -vE` filter drops template placeholders (`YYYY-MM-DD`, `WNN`, `<slug>`) and jq tempfile names (`data/.jq_update.tmp`) — these are *intentional* non-existent paths in conventions and code examples, not drift.

   - **Tool-usage contradictions** — CLAUDE.md forbids certain tools on structured data. Grep secondary docs for the forbidden forms:
     ```bash
     grep -rnE 'via sed|sed.*ndjson|echo.*>>.*\.ndjson|sed -i.*ndjson' \
       --include='*.md' docs/ CLAUDE.md AGENTS.md 0-me/ 1-values/ README.md \
       4-projects/AGENTS.md 5-actions/AGENTS.md 6-habits/AGENTS.md data/AGENTS.md \
       | grep -vE '^docs/superpowers/|forbidden|never|do not|no raw'
     ```
     Preferred form for any NDJSON edit is `jq` with a temp file. Flag any remaining recommendation of `sed`, `awk -i`, `echo >>`, or raw `>>` appends targeting NDJSON.

   - **Env-var coverage** — every var in `.env.example` should be referenced by at least one script or skill, and every env var read by a script/skill should be declared in `.env.example`. Tracked vars currently include `CLAUDE_CODE_OAUTH_TOKEN`, `GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`, `GOOGLE_HEALTH_TOKEN_FILE`, `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_INBOX_LIST_ID`, `TRELLO_DASHBOARD_BOARD_ID`, `LOCAL_TZ`. Trello credentials back the `pfc-trello-inbox` skill via `automations/scripts/trello_helper.py`, the `pfc-render-trello` skill via `automations/scripts/trello_render.py`, and the `pfc-sync-trello` skill via `automations/scripts/trello_writeback.py`. Whether `.env` itself has values populated is **informational only** — the audit never fails on missing local secrets.
     ```bash
     # Vars declared in .env.example
     grep -oE '^[A-Z_][A-Z0-9_]*=' .env.example | sed 's/=$//' | sort -u > /tmp/env-declared.txt
     # Vars actually referenced in code/skills
     grep -rohE '\b[A-Z_]{4,}[A-Z0-9_]*\b' automations/scripts/ .agents/skills/ \
       | grep -E '^(CLAUDE_CODE|GITHUB|GOOGLE_HEALTH|TRELLO)_' | sort -u > /tmp/env-used.txt
     # Declared but not referenced
     comm -23 /tmp/env-declared.txt /tmp/env-used.txt
     # Referenced but not declared
     comm -13 /tmp/env-declared.txt /tmp/env-used.txt
     ```

   - **Deprecated vocabulary** — concepts removed from the system should not still be referenced in live docs. Current list:

     | Old | New | Date stripped |
     |---|---|---|
     | (add deprecated terms here as your vocabulary evolves) |  |  |

     ```bash
     # Build a regex from the Old column of the table above, then:
     # grep -rnE "<old1>|<old2>|..." \
     #   --include='*.md' \
     #   CLAUDE.md AGENTS.md README.md docs/ 0-me/ 1-values/ 2-areas/ .agents/skills/ \
     #   4-projects/AGENTS.md 5-actions/AGENTS.md 6-habits/AGENTS.md data/AGENTS.md
     ```

     Track vocab migrations here so audits catch stale references.

     Expected exceptions: this skill file itself contains the table and example regex — those are the registry, not drift.
     Report any hits. **When deleting a file or concept, append it to this table** so future audits catch lingering references.

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

   # (d) Integration references intact
   grep -q 'revive_watchlist\.py' .agents/skills/pfc-morning-checkin/SKILL.md \
     && echo "morning-checkin→revive_watchlist.py:OK" \
     || echo "morning-checkin→revive_watchlist.py:MISSING"
   grep -q 'pfc-revive' .agents/skills/pfc-weekly-checkin/SKILL.md \
     && echo "weekly-checkin→pfc-revive:OK" \
     || echo "weekly-checkin→pfc-revive:MISSING"
   grep -q 'pfc-revive' AGENTS.md \
     && echo "AGENTS.md→pfc-revive:OK" \
     || echo "AGENTS.md→pfc-revive:MISSING"
   ```

   Any `MISSING` / `PARSE-FAIL` / `RUN-FAIL` → 🔴 in the report. The script-run check (c) is the load-bearing one — a passing parse doesn't catch broken jq filters inside the script.

7. **Report:**

   Output a table sorted by severity:

   | Severity | Domain | Issue | Location | Proposed fix |
   |---|---|---|---|---|
   | 🔴 | validator | … | … | … |
   | 🟡 | integrity | … | … | … |
   | 🟢 | docs | … | … | … |

   Then a numbered action list. Autonomously fix trivial drift (normalize enum typos, rewrite dead link paths, patch a stale field in a doc). For anything with judgment stakes (delete a file, merge skills, restructure docs), present the option and wait for the user.

8. **Commit** (if autonomous fixes were made):
   ```bash
   git add -A && git commit -m "system: repo maintenance [YYYY-MM-DD]" && git push
   ```
   If only reports were generated (no fixes), don't commit.

## What this skill is NOT

- **Not `/pfc-system-health`** — that skill audits *life-data completeness* (check-ins, habits, stale tasks needing user action). This skill audits *machinery* (schemas, references, docs).
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
