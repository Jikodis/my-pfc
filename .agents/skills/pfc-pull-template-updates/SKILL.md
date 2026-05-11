---
name: pfc-pull-template-updates
description: Pull updates from the upstream PFC template (Jikodis/my-pfc) into your fork. Walks commits one at a time so you can accept or reject each change. Use when the user says "pull template updates", "update from upstream", "what's new in the template", "/pfc-pull-template-updates", or "sync my fork with upstream".
---

# Pull template updates from upstream

## What this is

The PFC template lives at `github.com/Jikodis/my-pfc`. When you forked it, your fork became its own thing — your edits, your priorities, your life context. The upstream template keeps evolving: new skills, refined workflows, scrubs of leftover personal anchors, install-doc improvements, etc.

This skill is the **opt-in** way to bring those upstream changes into your fork, walked commit-by-commit so you choose what lands.

## Read this before pulling — three caveats

1. **The maintainer (Alex Bush) tailors the template to his own workflows.** Some changes will fit you; some won't. Drop the ones that don't on a per-commit basis. The template's whole shape — VAVPAH, 2+1 daily focus, 30+ skills, the persona system — was built around how *one specific brain* operates well. Defaults assume ADHD/autism/executive-function variants, but no two profiles in that audience are identical. The system was always meant to be edited; pulling updates is no exception.

2. **Upstream changes may clash with your modifications.** If you've heavily customized a skill, an area, the daily-focus model, or anything else, an incoming change to the same file produces a merge conflict. You decide which side wins. **Your modifications take priority** unless you actively want the new behavior.

3. **You don't need to pull updates.** Forks that never re-sync with upstream are entirely valid. Pull when you're curious or when a specific upstream change interests you — not because you "should" stay current.

If a default doesn't fit your life, **modify it locally instead of fighting upstream.** That's the spirit of the original `meta/system-is-editable` lesson. Pulling updates is not a path to alignment with the maintainer's life — it's a path to inheriting refinements you actually want.

## Prerequisites

1. **`upstream` git remote pointing to `Jikodis/my-pfc`.** If you don't have it:
   ```bash
   git remote add upstream https://github.com/Jikodis/my-pfc.git
   ```

2. **Your fork's `main` is clean** (no uncommitted changes) before starting. Commit or stash first.

## Workflow

### Step 1 — Fetch upstream + identify candidate commits

```bash
git fetch upstream
git log main..upstream/main --pretty=format:'%H|%s' --reverse
```

The list (oldest first) is the candidate set. If empty: your fork is already current with upstream. Stop.

### Step 2 — Group by category

Read each commit subject. Group into:

| Category | What it means |
|---|---|
| **Scrubs / personal-data fixes** | Maintainer found something personal-leaning that crept into the template and cleaned it up. Almost always safe to take. |
| **New skills / features** | New `pfc-*` skill, new install doc, new automation. Take if it fits your life; skip if not. |
| **Refined defaults** | Changes to existing skill behavior, schema fields, onboarding text. Read carefully — these are most likely to clash with your customizations. |
| **Docs / examples** | README, install guides, conventions. Usually low-risk. |
| **Trello / integration changes** | If you don't use that integration, skip. |

Surface the grouping to the user before walking commits.

### Step 3 — Walk each commit (oldest first)

For each commit:

```bash
git show --stat "$SHA"     # files changed at a glance
git show "$SHA"            # full diff
```

Ask the user: **Apply this commit?**

- **yes** → cherry-pick: `git cherry-pick "$SHA"`. If conflicts: stop, let the user resolve, then continue or abort.
- **no** → skip, log decision
- **defer** → skip for now, but remember it (the user might want it later)

Going oldest-first matters: later commits sometimes depend on earlier ones. Skipping an earlier one and taking a later one can produce conflicts the user can't easily reason about. If they skip an early one, warn that downstream commits may not apply cleanly.

### Step 4 — Conflict handling

Most conflicts will be one of:

- **You modified a skill the maintainer also touched.** Decide whose version wins. Often: keep yours, take only the parts of upstream you specifically want.
- **A file was renamed upstream but you'd already deleted it.** Drop the cherry-pick — `git cherry-pick --abort`, mark the commit "no."
- **A file the cherry-pick adds is one you already created with different content.** Decide.

After resolving manually:
```bash
git add <files>
git cherry-pick --continue
```

Or to bail:
```bash
git cherry-pick --abort
```

### Step 5 — Summarize and commit

After all candidate commits are processed:

```bash
git log main..HEAD --oneline    # what got applied
```

If the user is satisfied, push to their fork (which is `origin`):

```bash
git push origin main
```

If they want to back out the whole session:

```bash
git reset --hard origin/main
```

## What this skill never does

- Auto-cherry-pick without your approval per commit.
- Force-push or rewrite history on your fork.
- Touch your private data (`5-actions/_data/`, `6-habits/_data/`, `data/`, `notes/`, etc.) — those files are yours; upstream rarely touches them. If a commit somehow modifies one of these, **flag and skip by default** — it's almost certainly not what you want.

## When NOT to pull

- You've heavily customized core skills and the upstream changes would force you to re-do that customization.
- You're in the middle of a daily/weekly check-in or any other system run.
- You haven't committed your recent edits.
- You don't recognize the upstream maintainer's name and aren't sure you trust the source.

## Going the other direction — contributing back

If you found a generic improvement that other users might want, open a PR against `Jikodis/my-pfc`. Personal additions (your specific values, areas, skills tailored to your workflows) belong only in your fork.
