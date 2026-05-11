# Areas

Areas are the life domains the system tracks against. Every project, habit, and strategic task declares an `area:` field that must match one of these folder names — that linkage lets the system check whether you're working on what actually matters across your life, not just whatever's loudest.

This file is documentation; the canonical area set is **the list of folders alongside this README**.

## How to use this folder

- Each folder represents one area of your life.
- Each folder has a `statement.md` describing what "success" looks like in that area (filled in over time — initial state is a stub).
- Drop reference notes, plans, or research into the folder as second-brain material for that area. The system reads from `_data/` files (life-wheel, household-status); free-form markdown is yours to organize.

## Shipped areas — keep, delete, or rename freely

The template ships with a starter set of 12 areas. They're a reasonable starting menu, not a prescription:

| Area | What it usually covers |
|---|---|
| career | Day job, professional development, work projects |
| family | Family relationships, parenting, family-of-origin |
| finances | Budgeting, savings, debt, retirement, taxes |
| health | Sleep, exercise, nutrition, medical |
| household | Home maintenance, cleaning, organization |
| learning | Skills, courses, books, study |
| legal | Wills, contracts, regulatory obligations |
| personal | Self-care, identity work, hobbies that aren't recreation |
| recreation | Play, leisure, hobbies you do for joy |
| relationship | Romantic partnership |
| social | Friendships, community, networking |
| spiritual | Faith, meditation, meaning-making |

**Customize this list aggressively before you start logging real data.** Once tasks, habits, and projects point at an area, deleting it requires cleaning up those references first (the validator will flag the broken links). On a fresh install, you can delete and rename freely — nothing references anything yet.

### To delete an area you don't need

```bash
rm -rf 2-areas/<area-name>
```

Example: if "Legal" isn't a meaningful domain for you right now, run `rm -rf 2-areas/legal`. The system will simply stop tracking it.

### To rename an area

```bash
mv 2-areas/<old-name> 2-areas/<new-name>
```

Then update any references to the old name in tasks/projects/habits. On a fresh install there are no references, so the rename is free.

### To add a new area

```bash
mkdir 2-areas/<new-area>
cp 2-areas/career/statement.md 2-areas/<new-area>/statement.md
```

Edit the new `statement.md` to describe what success looks like in that area.

## Common customizations

- **Single? No "relationship" area needed yet.** `rm -rf 2-areas/relationship` — you can recreate it later.
- **Non-religious? "Spiritual" may not fit.** Either delete it or rename to something that does ("meaning", "philosophy", "stoicism").
- **Living with roommates, not partner?** Drop `relationship`, lean on `social` instead.
- **Small footprint life?** You don't need 12 areas. Some users run with 5–6 (career, health, family, finances, personal).
- **Specialized life?** Add what you need — `craft`, `parenting`, `research`, `community-leadership`, `creative-project`.

The right number of areas is whatever you'll actually engage with. Pruning is healthier than aspiration.

## Area statements

Each `<area>/statement.md` answers: *what does success look like in this area?* It's built up over time, not written all at once. The system surfaces these during weekly check-ins and uses them to push back when a project drifts away from what you said matters here.

Run `/pfc-onboarding areas/area-statements` for a guided walkthrough.

## The Life Wheel

`_data/life-wheel.ndjson` holds monthly ratings for each area (typically 1–10). It feeds the monthly check-in and gives you a longitudinal view of which areas are thriving vs. starving. The Trello dashboard surfaces it as a colored label on each area card.

## Schema integrity

The validator enforces that every `area:` field in `tasks.ndjson`, `projects.ndjson`, and `habit_schema.yaml` resolves to a folder under `2-areas/`. If you delete an area that's referenced, the validator fails — fix the references first, then delete the folder.
