---
name: pfc-pull-template-updates
description: Pull updates from the upstream PFC template (Jikodis/my-pfc) into your fork — safely, selectively, and without losing your data. Walks each upstream release, lets you take part of one and decline the rest, migrates your existing records to any new schema, and verifies the result. Use when the user says "pull template updates", "update from upstream", "what's new in the template", "/pfc-pull-template-updates", "upgrade to the latest version", or "sync my fork with upstream".
---

# Pull template updates from upstream

## What this is

The PFC template lives at `github.com/Jikodis/my-pfc`. When you forked it, your fork became its own thing — your edits, your priorities, your life in the data files. The upstream template keeps evolving: new skills, refined workflows, new schema fields, install-doc improvements.

This skill brings those changes in **on your terms**. Three guarantees, in priority order:

1. **Your data is never overwritten.** Not your tasks, habits, day tracking, projects, focuses, notes, values, areas, or personal files. Ever.
2. **You take only what you want** — down to individual files inside a release, not all-or-nothing.
3. **What you take actually works afterward** — schema changes come with a migration for the records you already have.

## Read this before pulling — three caveats

1. **The template is tailored to one person's workflows.** Some changes will fit you; some won't. Drop the ones that don't. The template's whole shape — VAVFPTH, the 2+1 daily focus, the skills, the persona system — was built around how *one specific brain* operates well. Defaults assume ADHD/autism/executive-function variants, but no two profiles in that audience are identical. The system was always meant to be edited; pulling updates is no exception.

2. **Upstream changes may clash with your modifications.** If you've customized a skill, a schema, or a config file, an incoming change to the same file conflicts. **Your version wins by default** — take upstream only where you actively want the new behavior.

3. **You don't need to pull updates.** Forks that never re-sync are entirely valid. Pull when a specific change interests you — not because you "should" stay current.

If a default doesn't fit your life, **modify it locally instead of fighting upstream.**

---

## The protected list — files this skill will not let upstream overwrite

Everything below is **yours**. Upstream ships these as *empty or example-filled starters*; your copies are full of your life. An upstream version of one of these files is never more correct than yours.

| Path | What's in it |
|---|---|
| `6-tasks/_data/*.ndjson` (`6-actions/_data/*.ndjson` in older forks) | tasks, task events, daily focus, archive |
| `7-habits/_data/*.ndjson` | habit logs |
| `5-projects/_data/*.ndjson` | project registry |
| `4-focus/_data/*.ndjson` | Current Focus records |
| `3-visions/_data/*.ndjson` + `3-visions/*.md` | visions, vision brainstorm |
| `2-areas/**` | area statements, life wheel, area items and check-ins |
| `1-values/values.md` | your ranked values |
| `0-me/**` | profile, working-with-me, schedule patterns, questions |
| `data/*.ndjson`, `data/health-raw/**` | day tracking, insights, findings, hypotheses, supplements, grounding, review ledger |
| `notes/**` | generated + written notes |
| `config/habit_schema.yaml` | **your habit definitions** — the most-customized file in the repo |
| `config/trello_calendar_filters.yaml`, `config/automation_config.yaml`, `config/persona.yaml` | your tuned config |
| `.env` | never tracked; never touched |

**The rule: for a protected path, take the *idea* and hand-apply it. Never take the file.**

An upstream commit that "adds" `6-tasks/_data/tasks.ndjson` is adding an **empty starter**. If you accept it over a populated file, your tasks are gone. That is the single most likely way to lose data in this workflow, and Step 3's guard exists to catch exactly it.

---

## Prerequisites

1. **An `upstream` remote:**
   ```bash
   git remote add upstream https://github.com/Jikodis/my-pfc.git   # once
   git remote -v | grep upstream
   ```

2. **A clean working tree.** Commit or stash first — `git status --porcelain` must be empty.

---

## Step 0 — Snapshot, so every step is reversible

Non-negotiable. Do this before touching anything:

```bash
STAMP=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y%m%d-%H%M')
git tag "pre-template-sync-$STAMP"          # rollback point
git switch -c "template-sync-$STAMP"        # work on a branch, never on main
```

Everything from here happens on that branch. `main` is untouched until you merge deliberately in Step 7.

**Full rollback at any moment:**
```bash
git cherry-pick --abort 2>/dev/null; git switch main
git branch -D "template-sync-$STAMP"
```
Your data is also still in the tag, so even a catastrophic mistake is `git restore --source="pre-template-sync-$STAMP" -- <path>` away.

Also capture a baseline of system health, so you can tell *your* pre-existing issues from ones the update introduced:

```bash
scripts/validate.sh > "/tmp/validate-before-$STAMP.txt" 2>&1; echo "exit=$?"
```

---

## Step 1 — List the candidate releases

```bash
git fetch upstream
git log main..upstream/main --no-merges --reverse --pretty=format:'%h|%ad|%s' --date=short
```

**`--no-merges` is required.** Upstream `main` carries GitHub merge commits; `git cherry-pick` on a merge commit fails outright (`is a merge but no -m option was given`). The real content lives in the non-merge "Template update …" commits.

Empty output → your fork is already current. Stop.

Upstream ships **one squashed commit per release**, so expect a handful of very large commits rather than many small ones. That is why Step 4 works at file granularity: a release is a menu, not a single yes/no.

---

## Step 2 — Summarize each release before touching it

For each candidate, show the user what it contains — grouped by *what it means for them*, not by file path:

```bash
git show --stat "$SHA" | head -40
git show "$SHA" -- README.md | head -30    # the stamp line + any release notes
```

Group into:

| Category | Default stance |
|---|---|
| **New skill / new automation** | Take if it fits your life. Additive, low risk. |
| **Refined behavior in a skill you use** | Read the diff. Most likely to clash with your customizations. |
| **Schema change** (`config/*_schema.yaml`, `scripts/validate.sh`) | Take *with* the matching migration in Step 5, or skip both. Never take the validator without the schema. |
| **Docs / examples** | Low risk. |
| **Integration you don't use** (Trello, TRMNL, health) | Skip freely. Nothing else depends on it. |

Present this summary and let the user choose per release: **take all · take some · skip · defer**.

---

## Step 3 — The data guard (run before every cherry-pick)

Before applying anything, list which protected paths the commit touches:

```bash
git show --name-only --format= "$SHA" | grep -E \
  '^(0-me/|1-values/values\.md|2-areas/|3-visions/|4-focus/_data/|5-projects/_data/|6-tasks/_data/|6-actions/_data/|7-habits/_data/|data/|notes/|config/(habit_schema|trello_calendar_filters|automation_config|persona)\.)' \
  || echo "clean — no protected paths in this commit"
```

**Any output is a stop sign.** For each hit:

1. Check whether your local copy has real content:
   ```bash
   wc -l <path>          # yours
   git show "$SHA":<path> | wc -l    # upstream's
   ```
2. If yours is non-empty → **never take the file.** Use partial adoption (Step 4) to exclude it, then hand-apply the *idea* (Step 5).
3. If yours is genuinely empty/absent and upstream's is a useful starter → taking it is fine.

**Special case — upstream moved a folder.** Releases sometimes renumber the VAVFPTH folders (`6-habits/` → `7-habits/`, `data/focus.ndjson` → `4-focus/_data/focus.ndjson`). The commit then reads as *"add an empty file at the new path"* while your populated file sits at the old path. Do **not** accept the empty file and do **not** let your old one linger. Move yours:

```bash
mkdir -p 7-habits/_data
git mv 6-habits/_data/habits-daily.ndjson 7-habits/_data/habits-daily.ndjson
```

Then take the commit *excluding* that path. Your records keep their history and land where the new code looks for them.

### Older forks: `6-actions/` is now `6-tasks/`

The Actions layer was renamed Tasks: the folder `6-actions/` became `6-tasks/`, and the acronym VAVFPAH became VAVFPTH. If your fork still has `6-actions/`, move the whole folder **before** taking any release that mentions `6-tasks/`, so your data moves with its history and nothing upstream ships lands on top of it:

```bash
[ -d 6-actions ] && [ ! -e 6-tasks ] && git mv 6-actions 6-tasks
git commit -m "system: rename 6-actions/ to 6-tasks/ (keep my data)"
```

If an earlier partial pull already created an empty `6-tasks/_data/`, check with `wc -l` that each upstream file there is an empty starter, then move your files over it one by one (`git mv -f 6-actions/_data/tasks.ndjson 6-tasks/_data/tasks.ndjson`, and so on) and remove the empty old folder. Afterward, update your own references: `grep -rn '6-actions\|VAVFPAH' --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml' .` should find nothing you wrote. If you added Trello lists or scripts of your own that name the `✅ Actions` list, rename those to `✅ Tasks` too.

### Older forks: instructions move from `CLAUDE.md` to `AGENTS.md`

`AGENTS.md` is now the only instruction file, at the root and in any subfolder that needs one. Claude Code reads `AGENTS.md` directly, and a `CLAUDE.md` at or above the working directory switches that off, so nested `AGENTS.md` files stop loading. If your fork has any `CLAUDE.md` files:

1. List them: `git ls-files | grep -E '(^|/)CLAUDE(\.local)?\.md$'`.
2. For each one, move every rule you wrote into the `AGENTS.md` in the same folder (create it if needed). A file that only says `@AGENTS.md` has nothing to move.
3. An area index at `2-areas/<area>/CLAUDE.md` becomes `2-areas/<area>/AGENTS.md`: `git mv 2-areas/<area>/CLAUDE.md 2-areas/<area>/AGENTS.md`.
4. Delete the emptied `CLAUDE.md` files (`git rm`), then grep your docs for "CLAUDE.md" and point them at `AGENTS.md`.

Do this as its own commit before taking a release that deletes the upstream `CLAUDE.md` files, so your own rules are never lost in a cherry-pick.

---

## Step 4 — Apply, selectively

### Whole release

```bash
git cherry-pick "$SHA"
```

### Part of a release (the common case)

Stage it without committing, then drop what you don't want:

```bash
git cherry-pick -n "$SHA"            # apply to index + worktree, no commit

git status --short                   # review everything staged

# Drop any protected or unwanted path, restoring YOUR version:
git restore --staged --worktree -- config/habit_schema.yaml
git restore --staged --worktree -- 6-tasks/_data/

git commit -m "template: adopt <what> from upstream $SHA (excluded: <what and why>)"
```

### A single file, ignoring the rest of the release

```bash
git checkout "$SHA" -- .agents/skills/pfc-plan-open-day/ docs/habit-mechanics.md
git commit -m "template: adopt the open-day planner from upstream $SHA"
```

This is the cleanest way to take one new skill out of a large release.

**When you adopt a new skill, recreate its symlink** — `.claude/skills/` entries are relative symlinks into `.agents/skills/`, and a rename upstream leaves a dangling one:

```bash
ln -sfn "../../.agents/skills/<name>" ".claude/skills/<name>"
find .claude/skills -xtype l -print        # any output = a broken symlink to fix
```

### Conflicts

| Situation | Resolution |
|---|---|
| You modified a skill upstream also changed | Keep yours; splice in only the specific behavior you want |
| Upstream renamed a file you deleted | `git cherry-pick --abort`, mark the release "skip" |
| Upstream adds a file you already created differently | Yours wins unless you prefer theirs |

```bash
git add <resolved-files> && git cherry-pick --continue    # proceed
git cherry-pick --abort                                    # bail out
```

Work **oldest release first** — later ones build on earlier ones. If the user skips an early release, warn that later ones may not apply cleanly.

---

## Step 5 — Migrate your existing records to any new schema

This is the step that makes an adopted schema change actually work. **A validator failure right after adopting a schema change is expected** — it is the system telling you which records need migrating, not a sign the update is broken.

The pattern, always:

1. Read the new schema (`config/*_schema.yaml`) and note which fields became **required**.
2. Backfill those fields on your existing records with safe defaults, **preserving every field you already have**.
3. Re-run the validator.

The `jq` shape — `. + {…}` adds the new keys and leaves everything else untouched, and `// ` only fills a field that is missing:

```bash
tmp=data/.jq_update.tmp
jq -c '. + {newfield: (.newfield // "default")}' <file>.ndjson > "$tmp" && mv "$tmp" <file>.ndjson
```

**Never** regenerate a data file from a template, and never hand-edit NDJSON with `sed` — migrate in place with `jq`, one field at a time, then check the diff.

### Worked example — the Current Focus vehicle/priority release

That release made `habits`, `impact`, `urgency`, and `parked` required on every focus record. Existing records fail two new validator checks. Backfill:

```bash
tmp=data/.jq_update.tmp
jq -c '. + {
  habits:  (.habits  // []),
  impact:  (.impact  // "medium"),
  urgency: (.urgency // "medium"),
  parked:  (.parked  // false)
}' 4-focus/_data/focus.ndjson > "$tmp" && mv "$tmp" 4-focus/_data/focus.ndjson
```

That clears the enum check immediately. The **vehicle check still fails by design**: `habits: []` means "this focus has no habit carrying it," which no default can decide for you. For each focus, either name the habit that is its vehicle (its id from `config/habit_schema.yaml`), or park/retire the focus. That choice is the point of the feature — see `docs/habit-mechanics.md`.

### Other migrations worth knowing

| Change | What you do |
|---|---|
| A ledger/registry gains a new row upstream (e.g. a new rolling-review item) | It's a **data** file — upstream's copy is not yours. Append the one new row yourself with `jq -cn '{…}' >> <file>` |
| A skill is renamed | Recreate the `.claude/skills/` symlink; grep your own docs for the old name |
| A field is removed upstream | Records keeping it are harmless — readers ignore it. Strip it only if you want to: `jq -c 'del(.oldfield)'` |
| A function signature changes in `automations/scripts/` | Only matters if you wrote custom callers. `grep -rn '<old_kwarg>=' automations/` |
| A cap is raised (projects, habits) | Nothing to do — looser limits never break existing data |

---

## Step 6 — Verify before you trust it

```bash
scripts/validate.sh                                   # compare against /tmp/validate-before-$STAMP.txt
python3 -m pytest automations/scripts/tests -q        # if you kept the test suite
git diff --stat "pre-template-sync-$STAMP"..HEAD      # everything this sync changed
```

Then confirm your data survived — counts should be **unchanged or higher**, never lower:

```bash
for f in 6-tasks/_data/tasks.ndjson 7-habits/_data/habits-daily.ndjson \
         data/day-tracking.ndjson 4-focus/_data/focus.ndjson; do
  [ -f "$f" ] && printf '%-45s %s\n' "$f" "$(wc -l < "$f")"
done
```

Compare to the same counts at the tag:

```bash
git show "pre-template-sync-$STAMP":6-tasks/_data/tasks.ndjson | wc -l   # 6-actions/_data/ if the tag predates the rename
```

**Any drop in a data-file line count means something overwrote your records — stop and roll back.**

Finally, run one real workflow end to end (`/pfc-status`, or an evening check-in) before calling it done. A green validator with a broken daily loop is not a successful migration.

---

## Step 7 — Land it, and record what you declined

```bash
git switch main
git merge --no-ff "template-sync-$STAMP"
git push origin main
```

Keep the `pre-template-sync-*` tag for a while — it costs nothing and is the fastest rollback you'll ever have.

**Log the decisions.** Anything declined will be offered again on the next pull, and future conflicts in that file won't make sense without the reason. Append to `docs/template-sync-log.md` (create it on first run):

```markdown
## 2025-01-15 — upstream abc1234

| Decision | Item | Why |
|---|---|---|
| Adopted | open-day planner skill | Weekends were unstructured |
| Adopted | focus vehicle habits (+ migrated 6 records) | Wanted the derived traffic light |
| Declined | Trello per-project lists | Don't use Trello |
| Declined | new habit_schema header | Would have clobbered my habits |
```

One line each. The "why" is the part that pays off six months later.

---

## What this skill never does

- Cherry-pick without your approval per release.
- Overwrite anything on the protected list.
- Force-push or rewrite history on your fork.
- Work directly on `main` (Step 0 branches first).
- Adopt a schema change without offering the matching data migration.

## When NOT to pull

- Mid-check-in, mid-review, or mid-anything — finish the run first.
- Uncommitted edits in the tree.
- You've heavily customized the core skills and would have to redo that work.
- You don't recognize the upstream source and aren't sure you trust it.
