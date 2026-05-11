# Me — personal context

This folder holds the personal context the agent uses to tailor its behavior to *you*. None of the system rules live here — those are in `AGENTS.md` at the repo root. Files here describe who you are, what your brain does, and how you want to collaborate.

## What lives here

| File | Purpose | Loaded |
|---|---|---|
| `profile.md` | Always-loaded ground truth — strengths, brain, accommodations | **Every request** (`@`-imported by AGENTS.md) |
| `working-with-me.md` | Long-form collaboration profile — pushback, decision authority, role and tone | On demand |
| `schedule-patterns.md` | Fixed weekly availability — office days, recurring commitments | On demand |
| `questions.md` | Open life questions you're sitting with | On demand |

Optional deep-reference files (`personality.md` for detailed assessment results, `core-psychology.md` for neuropsych eval) can be created during onboarding via `/pfc-onboarding meta/personality` and `/pfc-onboarding meta/core-psychology`. They are not shipped — most users don't need them.

## Out-of-the-box state

`profile.md` ships with conservative defaults that work for the target audience (ADHD / autism / executive-function variants):

- The **Brain** section has accommodations that fit most people in that audience — leave as-is until you have a reason to change.
- The **Who** section is mostly placeholders (motivators, anti-motivators, top values, love languages) — needs a 5-minute pass to be useful. The agent reads this every request, so the sooner you fill it in, the better the suggestions you get.

`working-with-me.md` ships with 8 sections of conservative defaults. Tailor §3 (pushback), §4 (decision authority), and §7 (role and tone) first if you only have 10 minutes.

`schedule-patterns.md` and `questions.md` are mostly stubs — fill in as it becomes relevant.

## Recommended early onboarding

Run these in order during your first session or two:

1. `/pfc-onboarding meta/set-local-timezone` — 30 seconds, fixes date stamping
2. `/pfc-onboarding meta/profile` — 5–30 min depending on whether you take assessments
3. `/pfc-onboarding meta/working-with-me` — 10–20 min for the three high-leverage sections
4. `/pfc-onboarding areas/areas` — prune the 12 default areas to what fits your life

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Strengths, personality, and core psychology — how the agent uses these files.
- Repo-root [`AGENTS.md`](../AGENTS.md) § Working with me — agent collaboration — the canonical collaboration rules.
