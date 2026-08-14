---
name: pfc-evening-checkin
description: Run the evening check-in workflow. Use when the user says "evening check-in", "end of day", "rate my day", "log my day", or "day review".
---

# Evening Check-in

**The daily spine.** There is no separate morning ritual and no weekly / monthly ritual check-in — this one workflow closes out today (focus review, habits, ratings), drips the reviews that are due, and pre-commits tomorrow's plan.

Five jobs, in order:

1. Close today — focus review, project status, habits, ratings.
2. Drip the **rolling reviews** — at most 2 due-and-actionable items (Step 3c).
3. Write the day record.
4. Refresh the dashboard.
5. Plan tomorrow — Current Focus trickle, tomorrow's 2+1, anchor-slot annotation (Step 4d).

---

## Step 0 — Derive the target date (CRITICAL)

The server clock is UTC. After your local evening crosses UTC midnight, the injected `currentDate` in your context is already tomorrow's date. Using it for evening check-in writes records to the WRONG day. Always derive the local date explicitly first:

```bash
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'
```

**Default:** use that output as `YYYY-MM-DD` in every step below. Do NOT substitute in the `currentDate` from context. Before writing any record, verify the date still matches the TZ-derived value.

**Past-midnight handling (00:00–04:59 local time):** if the local hour is < 5, the user is almost certainly closing out the *prior* calendar day, not the current one. Auto-shift the target date to yesterday and announce it in one line before proceeding (e.g. "Past midnight — targeting the previous day, closing out yesterday."). The user can override by naming today or a specific other date.

```bash
HOUR=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%H')
if [ "$HOUR" -lt 5 ]; then
  TARGET_DATE=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d')
else
  TARGET_DATE=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
fi
echo "$TARGET_DATE"
```

When past-midnight handling triggers, route through the backfill verification below (check the day-tracking record exists; warn if not).

**Backfill mode — "for yesterday" or an explicit date:** if the user says "run check-in for yesterday", "log yesterday", or names a specific past date, use that date instead. Compute yesterday as:

```bash
TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d'
```

Before proceeding, verify a day-tracking record already exists for the target date:

```bash
jq -c --arg d "YYYY-MM-DD" 'select(.date == $d)' data/day-tracking.ndjson
```

If it exists and the evening fields (`rating`, `energy`, `focus`, `mood`, `hyperfocused`) are null, proceed with Steps 1–5 using that date. If evening fields are already populated, confirm with the user before overwriting. If no record exists at all, warn the user and ask whether to append a fresh record for that date (Step 4's append branch).

---

## Step 0a — On-demand health fetch (fail-safe)

Pull the freshest health data for `$TARGET_DATE` **now**, at check-in time, so Step 3b's rating feedback and Step 4's record read tonight's actual sleep and activity — not a stale midday snapshot. Evening is the reliable moment: by now last night's sleep is fully synced (an early-morning fetch returns null sleep).

```bash
python3 automations/scripts/auto_fetch_health.py "$TARGET_DATE" 2>&1 | tail -4
```

The fetch **updates the day's row in place, keyed by date** — it never duplicates a row, and an unchanged fetch returns without committing. It also recomputes the record's `qqrt` sleep composite (via `backfill_qqrt.py`) after writing.

**Fail-safe:** on any error (health connector not configured, credentials unset, network/API failure), print `🟡 On-demand health fetch skipped (non-blocking): <reason>` and continue — the check-in reads whatever is already on the record. If no health connector is set up at all, skip this step silently.

**Backfill / past-date runs:** still fetch `$TARGET_DATE` — a past day's data is fully synced, so this just refreshes it.

---

## Step 0b — Pull Trello completions into repo (fail-safe)

Run **before** focus review and habit tracker so cards the user checked off via the phone widget land in `tasks.ndjson` and `habits-daily.ndjson` first. Otherwise Step 1 misreports focus completion and Step 2 prompts the user about habits already done on the widget.

```bash
python3 automations/scripts/trello_writeback.py sync 2>&1
```

Output is a JSON counters block (`tasks_completed`, `habits_logged`, etc.). On error: print `🟡 Trello sync failed (non-blocking): <error>` and continue — every later step reads from local NDJSON, so a missed sync only means the widget state isn't reflected; the check-in still completes.

If `TRELLO_DASHBOARD_BOARD_ID` is not set in `.env`, skip this step.

(The `move-back-uncompleted` and `render` halves of the Trello dance run later in Step 4b, after the day record is written.)

---

## Step 0c — Reconcile the inbox ↔ task system (fail-safe)

Run the **bidirectional Step 0 reconciliation** from [`pfc-email-triage`](../pfc-email-triage/SKILL.md) — this is where labeled emails enter the task system:

- **Reverse:** every open task linked to an email (`source_email_thread_id`) whose message left the inbox (archived or deleted elsewhere) → mark the task done with `source: "email-sync"` and append to `task_events.ndjson`.
- **Forward:** every labeled inbox email with no linked task → auto-create a task, priority derived from the label tier, area inferred from the subject, linked by `source_email_thread_id`. Dedup by thread id across live + archive.

Print one-line summaries (`📧 reconciled N task(s)` / `📧 auto-created N task(s)`). On any connector error: `🟡 email reconciliation skipped: <error>` and continue. If no email connector is configured, skip silently.

---

## Step 1 — Focus review

```bash
FOCUS=$(jq -c 'select(.date == "YYYY-MM-DD")' 6-actions/_data/daily-focus.ndjson)
```

**If `$FOCUS` is empty (no 2+1 was staged for today):** output one line — `No focus set today.` — and skip to Step 1b. Do not fabricate a checklist.

**Otherwise,** for each task (critical1, critical2, bonus, project if present), check completion status:

```bash
jq -c 'select(.id == "TASK-ID")' 6-actions/_data/tasks.ndjson
```

Show as a checklist — done or still open. Include the optional `.project` slot if it's set. Surface unfinished tasks without pressure.

**Ask once if anything was actually done that isn't reflected.** Widget completions land in Step 0b; if a focus task still shows open and the user might have finished it without checking the card, ask one line: "Any of these actually done that aren't checked off?" For each yes, route through `pfc-complete-task` so the task, the focus record, and any linked email all update consistently. Ask it even when everything already shows done (extra work may have happened). Skip the question only when zero focus tasks were set today.

---

## Step 1b — Active project status

Surface velocity for every active project so drift is visible at end-of-day.

```bash
jq -c 'select(.active == true)' 5-projects/_data/projects.ndjson
```

For each active project, render one line:

```
<name>  [====------] 40%  velocity X.X parts/wk → est <YYYY-MM-DD>  vs deadline <YYYY-MM-DD>  🟢|🟡|🔴
```

Velocity calc:
- `days_elapsed = today - started`
- `parts_per_day = completed_parts / max(1, days_elapsed)`
- `est_completion = today + ceil((total_parts - completed_parts) / parts_per_day)` if `parts_per_day > 0`
- 🟢 if `est_completion ≤ deadline` · 🟡 if ≤7 days late · 🔴 if >7 days late

If a project went 🔴 today, ask one question: "Want to reset the deadline, drop scope, or just note it?" — log the answer to the project file's notes field if any. Don't push a full re-plan at end of day.

---

## Step 2 — Habit tracker

```bash
# List ONLY active daily habits (the daily_habits: block) — id + description.
# Do NOT `cat` the whole schema: it also prints monthly_habits: and deprecated_habits:,
# and surfacing a retired habit here is an easy bug to introduce (see guard below).
awk '
  /^daily_habits:/      {b="d"; next}
  /^monthly_habits:/    {b="m"; next}
  /^deprecated_habits:/ {b="x"; next}
  /^[a-zA-Z_]/          {b=""}
  b=="d" && /^  - id:/          {sub(/^.*id:[ ]*/,""); gsub(/"/,""); id=$0}
  b=="d" && /^    description:/ {sub(/^.*description:[ ]*/,""); gsub(/"/,""); print id" — "$0}
' config/habit_schema.yaml
jq -c 'select(.date == "YYYY-MM-DD")' 7-habits/_data/habits-daily.ndjson
```

Show each **due-today** daily habit and whether it's been logged today. For any unlogged habits, ask if completed and offer to log inline.

**Show only habits due today.** A dozen daily habits in one nightly table turns the check-in into a chore, and degraded logging corrupts every derived focus light downstream. Build the shown set as:

- `frequency >= 5`/week → show every night.
- `frequency < 5`/week → show only if the week's reps are not yet met, counting from Monday. On the last night of the week with reps still owed, show it regardless.
- Monthly habits → show on the last 5 days of the month if the month's reps are not yet met, otherwise not at all.

A habit not shown is simply absent from the log — absence is interpreted as a miss at compute time, never written as one (`7-habits/AGENTS.md`). Do NOT write `completed: false` for a habit that was never shown. The "anything unmentioned in an active check-in logs as `completed: false`" convention applies only to habits that were actually shown.

**Guard — surface ONLY active daily habits, NEVER retired ones.** Ask about and log *only* the ids the awk above emits (the `daily_habits:` block). Anything under `deprecated_habits:` is retired — never ask about it, never log it. If a retired id gets logged by mistake, delete that entry from `habits-daily.ndjson`.

**Render the habit list as a TABLE, never a comma-separated inline list** — one row per habit, columns `Habit | State` (done / missed / skipped / **?** = unlogged, asking). A run-on list is hard to scan and habits get dropped in it. This holds any time a habit set is shown for confirmation.

**Three possible states per habit:** done, missed, or **skipped** (structurally unavailable — e.g. a shared-reading habit on a night the other person isn't there). If the user says "skipped", or the reason is obvious from context, log it with `skipped:true, completed:false, skip_reason:"..."` via the skip branch in `pfc-log-habit`. Skipped days drop out of completion math; missed days count against it. Default to **missed** when unclear — don't over-mark as skipped.

**Infer a structural skip from the calendar rather than asking, when you can.** If a habit depends on other people being present and an all-day calendar event says they're away (travel, a trip, someone else's week), auto-log `skipped:true` with the calendar event as `skip_reason` instead of asking. Note that all-day events use an exclusive `end.date`. If the calendar lookup fails, fall back to asking.

**Never miss twice.** After logging, check each shown habit for two consecutive misses:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
YDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d yesterday '+%Y-%m-%d')
jq -r --arg t "$TODAY" --arg y "$YDAY" \
  'select(.date==$t or .date==$y) | select(.completed==false and (.skipped//false)==false) | .habit_id' \
  7-habits/_data/habits-daily.ndjson | sort | uniq -c | awk '$1==2 {print $2}'
```

For each habit that comes back, print **one line** offering its `ramp.two_minute` from `config/habit_schema.yaml` — e.g. "Two in a row on guitar. Two-minute version: sit down and play one song." One miss is noise; say nothing. Two is the trigger. No lecture, no streak talk, and do not repeat it later in the same check-in. See [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md) § Never miss twice.

**Habits with an objective signal — pre-fill, don't ask blind.** If today's day-tracking `health` block already answers a habit (e.g. a tracked workout in `health.workouts` for an exercise habit), present it pre-filled for a one-tap confirm instead of asking cold. The habit log stays the source of truth — the health data is a prompt, not an auto-write.

**Bedtime-adjacent habits are asked RETROSPECTIVELY, for last night.** Habits that happen after the check-in (phone out of the bedroom, in bed by a target time, an evening wind-down) can't be known for tonight, and there's no morning ritual to catch them. Ask about them for **last night** and log them dated `$TARGET_DATE − 1 day`:

```bash
YESTERDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$TARGET_DATE -1 day" '+%Y-%m-%d')
```

Phrase the questions in the past tense ("Phone out of the bedroom last night?"). Guard against double-logging: skip either habit for the yesterday date if it's already present in `habits-daily.ndjson`. Do NOT log these for tonight's date — tonight's get asked at tomorrow's check-in.

---

## Step 3 — Ask evening questions

1. **Energy** (1–5)
2. **Focus** (1–5)
3. **Mood** (1–5) — the general sense of well-being **across the day as a whole**, not the peak moment. Take the number at face value; don't discount it for what happened in the day.
4. **Hyperfocused / inflexible today?** (yes/no — `hyperfocused` field)
5. **Evening notes** — one line reflection (optional)

**`rating` is DERIVED, never asked:** compute `round(mean(energy, mood, focus))` and store it (same rule as `pfc-log-day` — components beat an integrative guess, and many readers depend on the stored field).

Do NOT ask about sickness. Do NOT ask about sleep (auto-fetched in Step 0a). Do NOT ask an overall day rating.

**Never ask for a value that a habit already answers.** If the day record carries a field that mirrors a tracked habit (an exercise flag, a reading flag), derive it from the Step 2 habit log for the same date instead of adding a question.

**Do NOT tag or discount days for external events.** There is no `life_event` field. Events (a great evening, a concert, a milestone) are a normal, frequent part of a life, not noise to filter out — and since mood is rated for the day as a whole, a good number on an event day is a real reading. Never write a "the high mood was just the event" line into the record, the notes, or the chat. Describe what happened in `evening_notes`; that's it.

---

## Step 3b — Day rating feedback

After ratings are captured, offer a brief interpretation tied to today's observables, OR probe with one question when no signal is obvious. The point is to help the user notice the driver — not lecture, not narrate.

**Observables to scan (already in hand from earlier steps):**
- Focus completion ratio (Step 1: critical+bonus done / total)
- Manual habit completion (Step 2: done / tracked-manual)
- `hyperfocused` (Step 3 answers)
- Project velocity flags (Step 1b: any 🟡 or 🔴)
- Sleep + activity if auto-fetched onto the day's record (`health.sleep_hours`, `health.active_zone_minutes`)
- **Sleep timing** when available (`health.sleep_bedtime`, `health.sleep_wake_time` — ISO 8601 with timezone offset) — late bedtime and early wake often predict a low next-day rating independently of total hours. If the fields are absent, skip silently. Display in 12-hour AM/PM per the chat-time rule.

**Strong-signal patterns — name the driver in one sentence, then move on:**
- Rating 4–5, focus mostly done, habits mostly hit → "Focus and habits both landed — that tracks."
- Rating 1–2, focus mostly skipped → "Focus didn't land (X of Y done) — likely the rating driver."
- Rating 1–2 + `hyperfocused: true` → "Hyperfocus today."
- Rating 1–2 + short sleep (when health is populated) → "Short sleep last night usually shows up as low energy + mood."
- **Mismatch** (rating ≥ 4 but most focus skipped, or rating ≤ 2 but most done) → flag it and probe: "Rated 4 but 1 of 3 focus done — what made the day feel good?"

**No strong signal — probe with ONE question:**
- Rating ≤ 2: "Day rated low — anything specific that pulled it down?"
- Rating ≥ 4: "Day rated high — what worked?"
- Rating = 3: skip the probe. Neutral days don't need narrative.

If the user answers, append the answer to `evening_notes` (concatenated with the Step 3 reflection, separated by `; `) before Step 4 writes. Keep `evening_notes` under ~200 chars — trim if needed.

**Hard rules:** one sentence of interpretation max · one probe question max · skip entirely if ratings were skipped · don't probe on rating = 3 · don't repeat back the ratings just given.

---

## Step 3c — Rolling reviews

The old weekly / monthly / quarterly ritual check-ins are gone. Their review work is a **rolling ledger** (`data/review-ledger.ndjson`) that drips through the evening check-in — at most **2 items per night**, and only when something is genuinely due AND has something to act on. A no-review night stays as fast as any other; the ledger just re-checks tomorrow. `/pfc-review` runs the same ledger with no cap when reviews have piled up.

**Never surface more than 2. Never surface a due item whose gate is empty.** A due-but-empty-gate item silently passes (not shown, not stamped) and re-checks next night.

**What this step is NOT:** it does not re-implement any review workflow. Each surfaced item is a one-line pointer at the **owning skill** — the user runs that skill (or you offer to) if they want to act now. This step's job is to *notice what's due and point*, then stamp.

### 1. Compute gated candidates (due AND something to act on), most-overdue first, capped 2

Paste this whole block — it defines the gates, computes due items, filters to gate-non-empty, and prints the ≤2 to surface. Every gate fails safe to empty (missing file or script error → no crash, the item just doesn't surface).

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')

gate() {  # echoes a short reason if there's something to act on; empty otherwise
  case "$1" in
    stale-task-triage) python3 automations/scripts/revive_watchlist.py --today "$TODAY" 2>/dev/null | jq -e 'length > 0' >/dev/null 2>&1 && echo "slipped items" ;;
    tasks-missing-area) jq -c 'select(.status=="open" and ((.area//null)==null) and ((.project//"none")=="none"))' 6-actions/_data/tasks.ndjson 2>/dev/null | grep -q . && echo "tasks missing area" ;;
    focus-accuracy) jq -c 'select(.tier=="pursuit" and .retired_date==null and ((.landing//"")==""))' 4-focus/_data/focus.ndjson 2>/dev/null | grep -q . && echo "pursuit missing landing" || echo "weekly focus eyeball" ;;
    vision-relevance) ls 3-visions/*.md 2>/dev/null | grep -qv "README\|_template\|AGENTS\|CLAUDE" && echo "eyeball one vision" ;;
    habit-rate) echo "check trailing-7 habit rates" ;;
    values-alignment) jq -c 'select(.active==true and ((.values//[])|length==0))' 5-projects/_data/projects.ndjson 2>/dev/null | grep -q . && echo "project missing values" ;;
    day-trend-peek) [ "$(jq -rc 'select(.rating!=null)|.date' data/day-tracking.ndjson 2>/dev/null | tail -7 | wc -l)" -ge 5 ] && echo "trend peek" ;;
    hypotheses-review) CUT=$(date -d '14 days ago' '+%Y-%m-%d' 2>/dev/null); jq -c --arg c "$CUT" 'select(.status=="active" and ((.last_reviewed // "") < $c))' data/hypotheses.ndjson 2>/dev/null | grep -q . && echo "active hypotheses not reviewed in 14d" ;;
    life-wheel) echo "rate life areas" ;;
    household-status) [ -f 2-areas/_data/household-status.ndjson ] && echo "rate house areas" ;;
    project-progress) jq -c 'select(.active==true)' 5-projects/_data/projects.ndjson 2>/dev/null | grep -q . && echo "review active projects" ;;
    vision-activation) echo "lean-in / let-rest per vision" ;;
    monthly-habits) grep -q "monthly_habits:" config/habit_schema.yaml 2>/dev/null && echo "monthly habit rates" ;;
    insights-review) jq -c 'select(.status=="active")' data/insights.ndjson 2>/dev/null | grep -q . && echo "unreviewed insights" ;;
    findings-alignment) jq -c 'select(.status=="active")' data/findings.ndjson 2>/dev/null | grep -q . && echo "cross-check active findings" ;;
    trend-analysis) echo "deeper trend pass" ;;
    revive-outcomes) echo "revive outcomes ≥30d" ;;
    usage-audit) echo "usage check" ;;
    focus-repick|vision-brainstorm|strengths-refresh) echo "quarter turned" ;;
  esac
}

# Emit "overdue_days<TAB>id<TAB>label<TAB>tier" for items past cadence, most-overdue first,
# then keep only gate-non-empty items and take the top 2.
jq -rc --arg t "$TODAY" '
  ( ($t | strptime("%Y-%m-%d") | mktime) as $now
  | (.last_done | strptime("%Y-%m-%d") | mktime) as $ld
  | (($now - $ld) / 86400 | floor) as $age
  | select($age >= .cadence_days)
  | [ ($age - .cadence_days), .id, .label, .tier ] | @tsv )
' data/review-ledger.ndjson | sort -rn -k1,1 | \
while IFS=$'\t' read -r overdue id label tier; do
  reason=$(gate "$id")
  [ -n "$reason" ] && printf '%s\t%s\t%s\t%s\n' "$id" "$label" "$tier" "$reason"
done | head -2
```

**If the output is empty** → print exactly `No reviews due tonight.` and skip straight to Step 4. Do not manufacture a review.

### 2. Surface each (≤2) — one line pointing at the owning skill

For each surfaced `id → label → tier → reason`, print ONE line: the label, why it's up (`reason`), and the skill or action to run. Point; don't run the workflow inline unless the user says go. Owning-skill map:

| id | Owning skill / action to point at |
|---|---|
| `stale-task-triage` | `/pfc-revive` — walk the slipped watchlist |
| `tasks-missing-area` | assign an area to the flagged open tasks (`tasks.ndjson` / `/pfc-add-task` shape) |
| `focus-accuracy` | `/pfc-focus` — derived lights + landings; the four-way choice for anything red 2+ weeks (see `/pfc-review` § focus-accuracy) |
| `vision-relevance` | open one file in `3-visions/` and sanity-check it still fits |
| `habit-rate` | show trailing-7 completion per habit (from `7-habits/_data/habits-daily.ndjson`), then step any `ramp` frequencies — see `/pfc-review` § habit-rate |
| `values-alignment` | add `values` to the flagged active project(s) in `projects.ndjson` |
| `day-trend-peek` | quick eyeball of the last 7 day ratings (light `/pfc-analyze-trends`) |
| `hypotheses-review` | review active hypotheses in `data/hypotheses.ndjson` — update `last_reviewed`; graduate to a finding if the bar is met (n≥30, \|r\|≥0.3, p<0.01, or a clear lived-experience pattern). **Never auto-archive** — surface it, the user decides |
| `life-wheel` | rate the life areas (updates `2-areas/_data/life-wheel.ndjson`) |
| `household-status` | rate each house area (updates `2-areas/_data/household-status.ndjson`); create tasks for anything red |
| `project-progress` | `/pfc-summarize-project` per active project |
| `vision-activation` | `/pfc-focus` — lean in or let rest, per vision |
| `monthly-habits` | show monthly-habit completion (`7-habits/_data/habits-monthly.ndjson`) |
| `insights-review` | `/pfc-insights` — triage active insights |
| `findings-alignment` | cross-check active findings (`data/findings.ndjson`) against values, projects, and habits; supersede anything life has moved past |
| `trend-analysis` | `/pfc-analyze-trends` — full statistical pass |
| `revive-outcomes` | `/pfc-revive --review-outcomes` — outcomes of revived items ≥30d old |
| `usage-audit` | `/pfc-usage-audit` — is the system being used: data freshness, logging gaps, unused surfaces |
| `focus-repick` | `/pfc-focus` — quarterly re-pick |
| `vision-brainstorm` | `/pfc-vision-brainstorm` — dump what you want, then triage into visions / projects / focuses / habits |
| `strengths-refresh` | re-read `0-me/profile.md` (and any deeper personality / psychology files) and update what no longer fits |

Keep it soft — observation plus one low-friction next step. If the user engages (runs the skill, or says "did it" / "skip it this cycle"), that item is **engaged** → stamp it. If the user ignores it, do NOT stamp — it re-surfaces on cadence.

### 3. Stamp `last_done` on engaged items

For each engaged id, stamp today via the atomic temp pattern — one call per id:

```bash
ID="<engaged-id>"
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --arg t "$TODAY" 'if .id==$id then .last_done=$t else . end' \
  data/review-ledger.ndjson > "$tmp" && mv "$tmp" data/review-ledger.ndjson
```

Do not stamp an item the user ignored, and never stamp a due-but-empty-gate item (it never surfaced).

---

## Step 3d — Pulse readout (optional, fast)

If day-tracking has health data for today, show the lever pulse so the rating lands with context:

```bash
python3 automations/scripts/trello_render.py --pulse-history 7
```

One compact table (lever · today's value · target · 🟢/🟡/🔴 · 7-day trend). The trend prints a **days-on-target count** per lever — high is good (AGENTS.md § "Metrics point one direction"; never report these as miss-counts) — and flags chronic misses (on target ≤3 of 7) with the concrete fix. Surface at most the top 2 chronic misses; if there are none, one line ("pulse is holding") and move on. Skip silently if there's no health data yet — never block the check-in on it.

---

## Step 4 — Update record

First check whether a record already exists for the target date:

```bash
RECORD_EXISTS=$(jq -c --arg d "YYYY-MM-DD" 'select(.date == $d)' data/day-tracking.ndjson | head -1)
```

There is no `life_event` field — days are never tagged or discounted for external events (see Step 3).

**Branch A — a record already exists for the day (e.g. the health fetch created it):** update in place.

```bash
tmp=$(mktemp)
jq -c \
  --arg date "YYYY-MM-DD" \
  --argjson sick false \
  --argjson rating N \
  --argjson energy N \
  --argjson focus N \
  --argjson mood N \
  --argjson hyperfocused false \
  --arg notes "..." \
  'if .date == $date then . + {sick: $sick, rating: $rating, energy: $energy, focus: $focus, mood: $mood, hyperfocused: $hyperfocused, evening_notes: $notes} else . end' \
  data/day-tracking.ndjson > "$tmp" && mv "$tmp" data/day-tracking.ndjson
```

**Branch B — no record exists yet for the day:** append a fresh record with `null` for health fields (auto-fetch will backfill later).

```bash
jq -cn \
  --arg date "YYYY-MM-DD" \
  --argjson rating N \
  --argjson energy N \
  --argjson focus N \
  --argjson mood N \
  --argjson hyperfocused false \
  --arg notes "..." \
  '{
    date: $date,
    rating: $rating,
    energy: $energy,
    focus: $focus,
    mood: $mood,
    sick: false,
    hyperfocused: $hyperfocused,
    notes: null,
    evening_notes: $notes,
    health: {
      sleep_minutes: null,
      sleep_hours: null,
      awake_minutes: null,
      sleep_deep_minutes: null,
      sleep_rem_minutes: null,
      sleep_light_minutes: null,
      resting_hr_bpm: null,
      active_zone_minutes: null
    }
  }' >> data/day-tracking.ndjson
```

**Critical:** do NOT run Branch A's update-in-place jq against a missing record — the predicate silently never matches and every field drops on the floor with exit 0.

---

## Step 4b — Refresh Trello dashboard (fail-safe)

The completion-pull half of the Trello sync already ran in **Step 0b**. This step handles the post-record half: move uncompleted 2+1 cards back to ✅ Actions, then re-render so the board reflects today's writes.

**This step is fail-safe:** any error here is logged but does not block the commit step. If Trello is down, the check-in still records normally.

1. Move any uncompleted 2+1 cards back to ✅ Actions for tomorrow:
   ```bash
   python3 automations/scripts/trello_writeback.py move-back-uncompleted 2>&1
   ```
   On error: print `🟡 Trello move failed (non-blocking): <error>` and continue.

2. **Fetch Calendar, then render.** The evening check-in is the only daily loop, so it owns the daily refresh of the one calendar-fed list (`🗓️ Week at a Glance`) — the bare render skips that list, and no cron or git hook can reach the calendar connector. This mirrors `pfc-render-trello` Step 1; follow it for the exact JSON shape.

   a. **Calendar** — `mcp__claude_ai_Google_Calendar__list_events` on the in-scope calendars for the next 7 days from `$TARGET_DATE`, excluding the out-of-scope calendars listed in `docs/calendar-scheduling.md`. **Preserve `recurringEventId`** (the renderer uses it to drop recurring noise). Save to `/tmp/pfc-calendar-events.json`. If the calendar connector is unavailable, skip the fetch — the render then skips that list with a 🟡.

   b. **Render**, passing the calendar flag if the fetch succeeded:
   ```bash
   python3 automations/scripts/trello_render.py \
     --calendar-events /tmp/pfc-calendar-events.json 2>&1
   rm -f /tmp/pfc-calendar-events.json
   ```

   On any error (calendar fetch OR render): print `🟡 Trello render failed (non-blocking): <error>` and continue. A missed calendar fetch just leaves that list stale until the next render.

3. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step entirely.

---

## Step 4d — Plan tomorrow

Three durable planning jobs — trickle the quarter's Current Focus into view, pick tomorrow's 2+1, annotate tomorrow's anchor slot — so tomorrow's plan is pre-committed tonight instead of improvised in the morning.

```bash
TOMORROW=$(TZ="${LOCAL_TZ:-America/Denver}" date -d tomorrow '+%Y-%m-%d')
```

Use `$TOMORROW` everywhere below — never `$TARGET_DATE` (tonight's date, already closed out above) and never the raw `currentDate`.

**Wide-open-day check (runs first).** Before the 2+1 flow, test whether tomorrow is a wide-open day — the shape that reliably produces one accomplished thing out of ten. Two conditions, both required:

1. `TZ="${LOCAL_TZ:-America/Denver}" date -d "$TOMORROW" '+%A'` is Saturday or Sunday, or tomorrow is a holiday / known PTO day.
2. `list_events` for `$TOMORROW` (all in-scope calendars) shows **under ~2 hours** of hard commitments — timed, opaque, non-all-day events.

If both hold, offer it as a single line and let the user decide:

> 🟡 Tomorrow looks wide open — 1h of commitments on a Saturday. Want me to build an open-day plan now? (`/pfc-plan-open-day $TOMORROW`)

**If they say yes: invoke `pfc-plan-open-day` for `$TOMORROW` and skip the rest of Step 4d entirely** — no separate 2+1 pick, no anchor annotation. That skill folds tomorrow's anchor instance into the day's chain of blocks.

If they say no, or either condition fails, continue with the normal flow below.

Why this lives here and not in a morning ritual: a morning intention to run the planning skill goes invisible overnight. A plan built the evening before already exists at wake-up.

### Current Focus trickle (read-only)

Display what the user has chosen to be on this quarter *before* picking tomorrow's 2+1, so the picks are made with the quarter's focuses in view. Keeping a focus in perception is what keeps a long-running interest alive between the days you actually touch it.

```bash
python3 automations/scripts/focus_status.py --write
```

Show as one compact table — `Code | ● | Focus | Rate | Landing` — grouped by tier (🧱 Foundations first, then 🎯 Active Pursuits), sorted by `code` within each group. `●` is 🟢/🟡/🔴, or 🅿️ for parked. `Rate` is the primary vehicle's `<completed> of <target>`.

Print each focus's linked vision slug beside it when `link.type == "vision"` — identity is what keeps a long-running interest alive, and the vision line is the identity statement ("become a musician," not "practice guitar").

One line if nothing's off; note in a single line if a pursuit is 🔴 or has no landing. Don't turn this into a to-do — it's a reminder of trajectory. If any focus has `weeks_red >= 2`, note it in **one line** and point at `/pfc-focus` — do NOT run the four-way choice here. That belongs to the weekly `focus-accuracy` review; running it nightly makes it wallpaper. Full management is `/pfc-focus`.

**Back on track — one focus per night.** After the trickle table, when any focus is 🔴 or 🟡, pick exactly **one** and propose a single lowest-friction re-entry step for tomorrow. Selection: 🔴 before 🟡; rotate deterministically within that ordering (sort off-track focuses by status then title; index = day-of-month mod count) so consecutive nights spread across the set instead of hammering one item. The step comes from the focus's **landing anchor** — it is the external start trigger, not a discipline ask: "Guitar is 🔴 — want 10 minutes at the guitar tomorrow lunch, music on before you sit down?" If the user takes it and it's task-shaped, offer it as tomorrow's **bonus slot** in the 2+1 pick below (never a critical slot — recovery rides along, it doesn't displace). One item, one line, one offer, drop it silently on a no — never walk the full red list here; that's `/pfc-focus` and the weekly review. Skip entirely when nothing is off. The TRMNL `pfc-back-on-track` screen shows the whole off-track set ambiently; this step's job is converting one row of it into motion.

### Guard — already staged

```bash
jq -c --arg d "$TOMORROW" 'select(.date == $d)' 6-actions/_data/daily-focus.ndjson
```

If a record exists, show it and skip straight to Step 5 (Commit) — do not duplicate or re-pick.

### Pick tomorrow's 2+1 (+ optional project slot)

If not already set, check for carry-forwards from tonight's date — the record reviewed in Step 1 (`$TARGET_DATE`) is the "yesterday" relative to `$TOMORROW`:

```bash
jq -c --arg d "$TARGET_DATE" 'select(.date == $d)' 6-actions/_data/daily-focus.ndjson
```

**Carry-forward rule:** unfinished tasks from `$TARGET_DATE` auto-carry to `$TOMORROW`. Show them pre-selected and ask to confirm or swap. Only prompt for fresh picks if no carry-forwards exist.

Pull candidates, **excluding project tasks** (they get the optional 4th slot):

```bash
jq -c 'select(.status == "open" and (.project // "none") == "none" and (.deferred // false) == false)' 6-actions/_data/tasks.ndjson | head -15
```

Project tasks are pre-planned work and do NOT compete with standalone tasks for the 2 critical slots.

**Never offer a `deferred: true` task.** The user parked it — it's still open work, but they've said "not now, stop offering it." Deferred tasks stay out of every pick pool and out of the slippage watchlist until they ask for it back; don't nudge, don't count it as slipping. See `pfc-pick-tasks` Step 1.

**Exclude tasks already on the calendar on or after `$TOMORROW`** — they're already committed to a time. Tasks whose calendar event is *before* `$TOMORROW` and still open (overdue) DO stay in the pool. See `pfc-pick-tasks` for the fetch + filter recipe.

Suggest based on impact/urgency, then let the user pick 2 critical + 1 bonus.

**Top-priority tasks surface every day.** Rank the pool by `priority` (AA > AB/BA > … > CC; fall back to impact + urgency when unset) and always surface the top items regardless of tomorrow's day of week — including days the user usually rests. Day-of-week suitability may shape which *lower-priority* task rounds out the bonus slot; it must never keep a top-priority task off the list.

**Optional 4th slot — project task.** After the 2+1 is set, ask: "Add a project task as a 4th focus slot tomorrow? (yes / no / which project)". If yes, pull the **next-up** open task per project (lowest `sequence`, treating null as last):

```bash
jq -cs '
  map(select(.status == "open" and .project != "none"))
  | group_by(.project)
  | map(sort_by(.sequence // 999999) | .[0])
  | .[]
' 6-actions/_data/tasks.ndjson
```

This surfaces one task per project — the one that's actually next given dependency order. Skip the prompt if the result is empty.

**Respect the user's available windows when suggesting.** Personal tasks only land in the free windows declared in `0-me/schedule-patterns.md` (see `docs/calendar-scheduling.md` § Focus-task scheduling). Check **tomorrow's** day-of-week, not tonight's. If tomorrow's personal windows are mostly blocked, say so and prefer smaller tasks — don't pick an XL personal task for a day with 30 free minutes.

Log the focus record (omit `project` if no 4th slot was chosen):

```bash
jq -cn \
  --arg date "$TOMORROW" \
  --arg c1 "TASK-ID-1" \
  --arg c2 "TASK-ID-2" \
  --arg bonus "TASK-ID-3" \
  --arg proj "TASK-ID-4-or-empty" \
  '{date: $date, critical: [$c1, $c2], bonus: $bonus, completed: [], bonus_completed: false}
   + (if $proj == "" then {} else {project: $proj, project_completed: false} end)' \
  >> 6-actions/_data/daily-focus.ndjson
```

Never pull tasks from the calendar — calendar events are already built into the day.

### Annotate tomorrow's anchor slot

The 2+1 lives on **one recurring daily anchor event** — a single ~30-minute slot per day that already exists on the calendar. This step annotates **tomorrow's instance** with tomorrow's pre-committed tasks. Do NOT create per-task calendar events, and do NOT invoke `pfc-schedule-focus` from here.

**Anchor principle:** the slot is anchored to a *running state*, not a clock time — it bends out of something already happening (the end of the workday, right after exercise, right after a fixed weekly commitment). The clock time on the recurring event is just the usual case; the running state is the rule. If the anchoring activity moves, the slot moves with it. See `docs/calendar-scheduling.md` § the anchor rule.

Example shape (each user sets their own in the recurring events — one per distinct trigger):

| Day | Slot | Running state it bends out of |
|---|---|---|
| Weekdays | late afternoon, 30 min | end of the workday |
| Saturday | morning, 30 min | right after the morning workout |
| Sunday | afternoon, 30 min | after the day's fixed commitment |

**Slot-loss rule:** if a real conflict eats the slot *on the day*, that window is lost — no make-up, no rescheduling in the moment, otherwise the user spends the slot rescheduling the slot. Never drag the **recurring series** to dodge a conflict. This is about the live window only: the night before, a single colliding instance still gets moved to the nearest anchor-able slot and annotated (see below), and the 2+1 is always pre-committed regardless.

**What to do:**

1. Determine which anchor applies to `$TOMORROW`: `TZ="${LOCAL_TZ:-America/Denver}" date -d "$TOMORROW" '+%A'`.
2. Find tomorrow's recurring anchor event via `mcp__claude_ai_Google_Calendar__list_events` with a tight window around the expected slot, dated `$TOMORROW`. If a day has two alternating anchor events (biweekly pairs offset by phase), widen the window and take whichever instance exists that week.
3. **Check for a one-off collision first — then MOVE the anchor, never delete it.** If a one-off event (an appointment, a game, a birthday — anything that isn't the anchor itself or a transparent / all-day marker) overlaps tomorrow's slot, **`update_event` tomorrow's instance to the next free slot that bends out of a running state** — the end of the colliding event is usually the right anchor (post-game, post-appointment). Annotate it exactly as in step 4, and add one line to the description naming what it moved off and why. Print `🟡 anchor moved to <time> tomorrow — <event> sits on the usual slot.`

   **Never `delete_event` an anchor instance, and never skip the 2+1 because the clock slot was taken.** The anchor is a *container* that displays the day's picks; the picks are the point, the 30-minute window is not. A day with no anchor instance still gets a `daily-focus` record. On a wide-open day the whole day is available, so a taken slot costs nothing — say so in the moved-anchor line rather than treating the day as lost.

   If genuinely no free slot exists tomorrow, leave the instance where it is, annotate it anyway, and note the overlap in the description. Still write the `daily-focus` record.

   (A *recurring* conflict is handled structurally with alternating recurring events, not instance moves — see `docs/calendar-scheduling.md`.)
4. Otherwise update that instance's `summary` **and** `description` with tomorrow's picks, via `mcp__claude_ai_Google_Calendar__update_event` on the **specific instance** (pass `startTime` / `endTime` unchanged plus the new `summary` and `description`).

   **Title carries the two critical picks.** A bare `2+1 anchor` title means the slot arrives without saying what it's for, and the description is one tap too many on mobile at the moment the slot fires. Keep the anchor label, append short gists of the two critical tasks (~30 chars each, truncate with `…`):

   ```
   PFC - 🎯 2+1 (post-workout): Renew passport · Draft the deck
   ```

   Bonus and project slots stay in the description only — four items in a title is unreadable on a phone. Description format:

```
🎯 Tomorrow's 2+1:
  • Critical 1: <task title> (<task-id>)
  • Critical 2: <task title> (<task-id>)
  • Bonus: <task title> (<task-id>)
  • Project: <task title> (<task-id>)   [if a 4th slot was chosen]

Rule: bend the running state into the first task. A lost slot stays lost.
```

5. If no anchor event exists for tomorrow (the recurring series was moved or deleted), print `🟡 Anchor slot missing for <day>; consider re-creating the recurring event.` and continue — never block.

**Anchor must never drift from the pick.** Any later change to a day's 2+1 — a same-day re-pick, a single swap — re-annotates that date's anchor instance immediately. A focus write that leaves the calendar showing stale picks is a bug.

---

## Step 5 — Commit

```bash
git add data/day-tracking.ndjson 7-habits/_data/habits-daily.ndjson 6-actions/_data/daily-focus.ndjson data/review-ledger.ndjson
git commit -m "checkin: record YYYY-MM-DD"
git push
```
