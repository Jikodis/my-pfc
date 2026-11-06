---
name: pfc-stuck
description: Break out of frozen, locked-in, foggy, fatigued, or overwhelmed states. Use when the user says "stuck", "frozen", "can't start", "can't stop", "locked in", "nothing is clicking", "tired", "not functional", "overwhelmed", "overloaded", "fried", "irritable", "everything's too much", or "can't even".
---

# Stuck Protocol

When invoked, diagnose the *type* of stuck first, then deliver the matching intervention. Do NOT dump all five types at once — ask one question, get the answer, act.

**Tune this skill to yourself.** The types and levers below are the shipped defaults. The thresholds (sleep hours, awake minutes, "before noon") are starting points, not measurements of you — after a few weeks of `data/day-tracking.ndjson` you'll know your own numbers. Edit them here.

## Framing — say this once if it's the first time today

Stuck has **two poles. Both are dysregulation; both are fixed by changing inputs, never by willpower:**

- **Too little arousal (Types A–D):** the internal effort-vs-reward calculation returns "not worth it" before you consciously decide anything. Can't start, can't switch, foggy, tired.
- **Too much (Type E — overwhelmed):** accumulated sensory / social / masking load has pushed the arousal system past its ceiling. Capacity exceeded, irritable, everything reads "too much."

Both ends teach the same lesson: don't push the broken part harder — change the inputs. The interventions below raise the reward side, lower the effort side, or reduce the load. Use plain language; do NOT call any of this discipline.

**If this framing doesn't match your brain, edit it.** It's written for profiles where initiation is the weak layer rather than capability — see `0-me/profile.md` § Brain and § How to work with this brain.

## Step 0: Upstream-gate check (before anything else)

Two gates sit upstream of every Type A–D intervention: **sleep** and **whether today's anchor cardio has happened**. Most interventions below quietly assume baseline arousal is already online; if a gate is missing, the intervention bounces and you'll misdiagnose it as "the technique doesn't work."

Set `CARDIO_HABIT` to whatever anchor movement habit you track in `config/habit_schema.yaml` — vigorous cardio (rowing, cycling, a hard interval session) is the version that reliably moves arousal for most people in this profile; a gentle walk usually isn't enough.

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
CARDIO_HABIT="morning-walk"   # ← replace with your own anchor cardio habit id
SLEEP_H=$(jq -r --arg d "$TODAY" 'select(.date == $d) | .health.sleep_hours // empty'   data/day-tracking.ndjson | head -1)
AWAKE_MIN=$(jq -r --arg d "$TODAY" 'select(.date == $d) | .health.awake_minutes // empty' data/day-tracking.ndjson | head -1)
CARDIO=$(jq -r --arg d "$TODAY" --arg h "$CARDIO_HABIT" \
  'select(.date == $d and (.habit_id // .habit) == $h) | .completed' 7-habits/_data/habits-daily.ndjson | head -1)
```

### The sleep gate reads fragmentation, not just total hours

Total hours is the weakest single signal. A night can clear the hours floor and still produce a depleted day if it was broken up. The readout that matters alongside hours is **`awake_minutes`** — time awake inside the sleep window. A continuous night runs low single-digit minutes; a fragmented one runs many times that, at identical total hours, and it shows up as friction by midday.

**Gate fails if EITHER: total < ~5.5h, OR `awake_minutes` > ~30** (fragmented, even when total hours look fine). Both numbers are shipped defaults — check them against your own day-tracking history and edit.

When the sleep gate fails:

- **Lower the day's bar explicitly.** On a fragmented night, name it plainly: total hours can look adequate, but broken-up sleep is poor-quality sleep. Today's ceiling is a 3, not a 5 — don't let the day get measured against a recent clean-sleep day.
- **Default intervention is fatigue management (Type D).** Past noon on a fragmented night, **lead with a 10-minute yoga nidra (non-sleep deep rest, "NSDR")** rather than a nap — a late nap further damages tonight's already-fragile sleep, and NSDR restores without that cost. Then music + smallest well-defined task, chained directly off the end of the rest (the end of the rest is the running state to anchor to).
- **Continue the diagnostic below, but treat depletion as the primary blocker.** The fix is restore-then-start-small, not an initiation push against the wall.
- **The real fix is tonight:** protect a *continuous* sleep block. Surface that, not just a daytime technique.
- **Still do the cardio on a low-sleep day — but lighter.** Movement gives a partial lift even on a bad night and can nudge a 2 toward a 3, so don't skip it; it just can't compensate for the sleep deficit. Default to a moderate session rather than an all-out one: recovery is impaired on sleep loss and a redline session can deepen afternoon fatigue. Below ~5h, expect the day to be impaired regardless of levers.

### The cardio gate

**Cardio missing but accessible AND it's still morning:**
- Surface it as the primary lever BEFORE running the diagnostic. One sentence: "No cardio yet — 15–20 min vigorous, then re-assess. Baseline arousal coming online may resolve this without a structural fix."
- Hold the line per the rationalizations rule below; don't let "I'll do it later" close the prompt.
- If they do it: re-check state after, then run the diagnostic (Type A often becomes Type C, or resolves).
- If they decline or it's no longer morning: proceed to the diagnostic, but flag the cardio gate as the likely root cause and bias toward Type C interventions.

**Cardio missing and it's evening:** treat a movement burst (30 jumping jacks, sprint the stairs, 2 minutes max effort) as the parallel lever — same mechanism, faster. Same surface-first-then-diagnose pattern.

**Both gates fine:** proceed to the diagnostic.

## Step 1: Diagnose

Ask exactly this (keep it short — they're stuck):

> "Which fits right now?
> A — Can't start (frozen, spinning, avoiding)
> B — Can't stop (locked into one thing, ignoring everything else)
> C — Foggy / low energy (partially functional, nothing clicking)
> D — Physically tired (heavy eyelids, body wants rest)
> E — Overwhelmed (fried, irritable, everything reads 'too much')"

If they already named the type in their message, skip the question and go to Step 2.

**If several apply at once (e.g. A + C + D + E): that's usually ONE thing — depletion, an empty tank — wearing several masks, not four separate problems.** Default to *settle + refuel + protect tomorrow*. No initiation push. If something genuinely can't wait (a promise, a hard deadline), use the **mixed-state settle→activate sequence** in the lever menu below — never an activating spike while overwhelmed.

**Also establish context.** If it's not clear from their message, ask: "Work or personal?" This changes which task list Types A and C pull from. If they say work, do NOT pull from `6-tasks/_data/tasks.ndjson` — those are personal tasks. Use the work path below.

---

## Step 2: Intervene by type

**When the user rationalizes the suggestion away — hold the line.**

The typical rationalizations:
- "I don't have time"
- "I'm too busy with work / other tasks"
- "I'll do it later"
- "I don't really need it right now"

Don't accept any of these as the end of the conversation. State the position once, plainly:

> "This method works for you. You have permission to do it without overthinking. Body-state change comes first — the cognitive work goes better after, not before."

Don't argue or escalate. State it once and hold it.

### TYPE A — FROZEN (can't start)

**First:** put on energizing music RIGHT NOW. Don't negotiate — just press play. Music on *before* the chunk is the highest-yield, lowest-cost lever in this whole skill; it reliably flips "not worth it" to "fine" on low-reward work. Reaching for it *after* stalling for twenty minutes is too late to be cheap.

If music alone isn't moving you after a few minutes:

**Second:** while the music plays, pick the smallest clearly-defined task. Not "work on X" — something with a specific output finishable in 5–15 minutes.

**If personal context:**

```bash
jq -c 'select(.status == "open" and (.size == "XS" or .size == "S"))' 6-tasks/_data/tasks.ndjson \
  | jq -s -r 'sort_by(if .size == "XS" then 0 else 1 end) | .[:3][]
              | "[\(.size)] \(.id): \(.description) (\(.location))"'
```

Show the top 3 smallest. Tell them: **pick one, start it. Don't pick the best one — pick the first one that's clear.**

**If work context:**

Work tasks aren't in this system. Ask: "What's the work task you need to do?" Then decompose it with them:
- What is the very first *physical* action? (Open a file, write one function, send one message, read one doc)
- What does "done" look like for just the next 15 minutes?
- Give them one sentence: "Start by [specific first action]."

Same goal — formatted input lowers the activation threshold; ambiguity raises it. If they can't name a first action, that IS the blocker; spend 2 minutes decomposing before attempting anything.

If still frozen after 30+ minutes despite music:

**Third — state-change lever.** Reach for an **activating** lever (see the lever menu below; frozen is under-aroused, so move UP the curve):
- **Morning / daytime:** vigorous cardio, 15–20 minutes. When done, sit back down immediately — don't shower, don't check the phone — music still playing, start the micro-task.
- **Need it faster:** a movement burst (30 jumping jacks, sprint the stairs) or **cold exposure** (30–60s cold shower, or cold water on wrists and back of neck). Both raise arousal fast.
- **Evening, or cardio isn't accessible:** movement burst. Same mechanism, and the internal calculator reads it as "different mode now." After: same protocol — music on, micro-task.

**Fourth — anchor to a running state.** If something is already in motion (a meeting just ended, a meal just finished, music just started), chain the stalled chunk directly downstream so the two feel like ONE unit with no decision gap. This is the always-available external-start option and it requires no other person. If a person IS available at the start moment, use them as a bonus (hand-off, or text "starting now") — then solitude. Never co-work through the chunk.

**What NOT to do when frozen:** don't try to willpower through the big ambiguous task. Don't scroll as a warm-up. Don't substitute a gentle walk for the vigorous option — it usually won't clear the threshold. Don't suggest sticky notes, reminders, calendar blocks, or progress bars: object-based reminders go invisible within a couple of days for this profile.

---

### TYPE B — LOCKED IN (can't stop or switch)

Hyperfocus is a problem state by default. Break it.

**First:** vigorous cardio now, 15–20 minutes. This is the most reliable way to restore the flexibility needed to disengage. Afterward there's a brief window — use it consciously to choose what's next.

If cardio isn't accessible right now:

**Second:** stand up and leave the room the task is in. Different space, then 3–5 minutes of vigorous movement (jumping jacks, run in place). Environmental change plus movement can partially break the lock.

**Third — re-orient.** Read the day's 2+1 from `6-tasks/_data/daily-focus.ndjson`. Is the thing you're locked into actually one of them? If not, you're off-plan; switch to one of the 2+1 for at least 30 minutes before returning.

**Structural note:** ordinary alarms don't penetrate lock-in. What can work: an alarm that requires a physical action to dismiss (not a passive ping), a pre-set external obligation with real consequences (a pickup, a scheduled live event), or another person physically entering and talking to you. The most reliable always-available version is anchoring stop-time to a downstream *running state* — "cooking starts at X," "the household is home at Y" — rather than to a clock.

**What NOT to do when locked in:** don't set more alarms. Don't negotiate ("just 5 more minutes"). Don't substitute a walk.

---

### TYPE C — FOGGY (partially functional, nothing clicking)

**First — run the input diagnostic. Which input is missing?**

Ask or check:
- Cardio done today? (No → arousal is low)
- Eaten in the last ~4 hours? (No → low glucose degrades control and focus)
- Water in the last hour?
- Enough time in bed? (No → everything downstream is degraded)
- Medication taken, if you take any? (Log it in `data/supplements.ndjson`; a missed dose explains a lot of foggy days)
- Environment noisy or distracting? (Fix it: headphones, reposition, back to the wall)
- Is the task ambiguous? (Spend 10 minutes decomposing into explicit micro-tasks before attempting)

If any input is missing, fix it first — the system isn't broken, the inputs are.

**Second:** music + the *easiest* well-defined task on the list. Don't fight fog with your hardest task. Finishing something small generates the reward signal that may bootstrap a better state.

**Third:** if available, a midday cardio session. Won't turn it into a great day, but it can lift a 2 to a 3.

**Last resort:** accept the day. Early bedtime. One mediocre day plus a strong day tomorrow beats two mediocre days from pushing too hard tonight. Forgive it.

---

### TYPE D — FATIGUE (physically sleepy)

**Before noon:** 20-minute power nap, timer set exactly — longer risks sleep inertia. Dark, quiet. On waking, immediately apply Type A (music + micro-task) before the post-nap fog becomes a freeze.

**After noon:** don't nap — late naps damage tonight's sleep and make tomorrow worse. Two options:
- Cardio, 15–20 minutes, then use the post-exercise window for essential tasks and prioritize an early bedtime.
- **10-minute yoga nidra (non-sleep deep rest, "NSDR")** — a guided rest protocol. It restores energy with none of a nap's sleep inertia and no disruption to tonight's sleep, which makes it the safe after-noon option when cardio isn't accessible. Usable any time of day.

**If fatigue is chronic rather than just today,** go after root causes rather than repeating daytime patches:
- Consistent time in bed?
- Bedroom humidity in a comfortable range? (Dry air fragments sleep for some people)
- Nasal congestion or breathing obstruction?
- Sleep actually tracked? Check `awake_minutes` across the last two weeks — a persistent high number is worth a doctor's conversation, not another nap.

---

### TYPE E — OVERWHELMED (overloaded, irritable, "it's all too much")

The opposite end from frozen: not too little arousal, too much. Accumulated sensory / social / masking load — often plus hunger and no movement that day — has pushed the arousal system past its ceiling. The tells: irritability, zero tolerance, everything grating, and *trivial* tasks (one meal, one errand) reading "too much."

**This is overload, not anxiety and not a character failure.** The flooding usually isn't a feeling *about* the people around you — the buffer hit zero, so the same input you'd normally absorb now overloads. You cannot willpower patience out of overload; same rule as every other type — reduce the load, don't push the broken part.

**Trivial-task overwhelm is a gauge reading, not a to-do.** "Even this simple thing is too much" is one of the most reliable readouts available, especially if introspective self-report is unreliable for you. Trust it like a number on a wearable. The response is to *lower the bar*, never to push through.

**First — REDUCE INPUT.** 5 minutes of low stimulation: headphones, quiet or brown noise, step outside, one room with the door closed. This lets the arousal system fall back down the curve. Non-negotiable, before anything else.

**Second — EAT.** Low glucose degrades prefrontal control and amplifies irritability. Lowest-effort food available, now — cereal counts. If they haven't eaten, this is often half the problem.

**Third — LOWER THE BAR for whatever's next.** Drop demands. Route around any task that requires holding a sequence (one externalized step, or a zero-step food). Keep the rest of the block low-key. **If other people depend on you right now** — kids, a partner, anyone in your care — they need a regulated person more than a productive one: presence over activity, and one calm shared thing beats an ambitious plan attempted while fried.

**Fourth — settle, don't spike.** See the lever menu below; overwhelmed is over-aroused, so move DOWN the curve: a **physiological sigh** (double inhale, long slow exhale, ×3), **cold water on the face** (slows the heart), or **deep pressure** (heavy blanket). Do NOT use an activating lever here — a vigorous burst or a body cold shower drives arousal further into overload. Once settled, a gentle movement burst can re-up capacity if needed.

**What NOT to do when overwhelmed:** don't try to "be more patient" — willpower doesn't touch overload. Don't push through the task. Don't add stimulation (more noise, more screens, a new tab). Don't make them decide anything complex while flooded — give the one next move.

---

## Step 3: After the intervention — maintain the state

Once unstuck, remind them:
- Keep the music playing while working.
- Stay on the current task to a natural stopping point — each switch is expensive.
- Don't check the phone or social feeds; competing reward pulls you straight back out.
- Switching tasks on purpose: take a 30-second music break between them as a reset.
- On lock-in risk days, set a stop timer BEFORE entering deep focus — you won't be able to set it afterward.

---

## Quick reference

| Type | First try | Second | Third / last resort |
|---|---|---|---|
| Frozen | Music ON (before anything else) | Music + micro-task | Activate: cardio (AM) or a movement burst (PM); then anchor to a running state |
| Locked in | Cardio 15–20 min | Leave the room + vigorous movement | Anchor stop-time to a downstream running state; a person interrupting, if available |
| Foggy | Check inputs (sleep, cardio, food, meds) + music + easy task | Midday cardio or movement burst | Accept the day, protect tomorrow |
| Fatigue | 20-min nap (before noon only) | Cardio, or 10-min yoga nidra / NSDR (after noon — no nap downsides) | Fix the sleep root causes |
| Overwhelmed | Reduce input 5 min (quiet, headphones, step out) | Eat (low glucose amplifies it) | Lower the bar / route around; settle (sigh, cold water on face, deep pressure) |

---

## State-change lever menu (reference)

The goal is always the **productive middle of the arousal curve** — so the direction depends on which pole you're at. Pick from the matching column. Do NOT reach for an activating lever when overwhelmed: a hard spike pushes further into overload, not out of it.

**Why "more adrenaline" is the wrong target.** The useful lever is central brain arousal — what vigorous cardio raises. Peripheral adrenaline barely crosses into the brain, and a big spike is fight-or-flight, not clean arousal. A sharp activation helps only when *under*-aroused; the same spike when *over*-aroused makes things worse. Aim for the middle.

**Activate — move UP (frozen / foggy / low: Types A, C):**
- **Vigorous cardio, 15–20 min** — primary. Rowing, cycling, hard intervals; whatever you'll actually do.
- **Movement burst** when there's no equipment — 30 jumping jacks, sprint the stairs, 2 minutes max effort. Fast.
- **Cold exposure** — 30–60s cold shower, or cold water on wrists and the back of the neck. Cheap, fast, lasts a while.
- **Bright light** — step into sunlight or under a bright lamp. Raises alertness, with a circadian bonus.
- **Upbeat or intense music** — on *before* the chunk.

**Settle — move DOWN (overwhelmed / irritable / fried: Type E):**
- **Reduce input** — headphones, quiet, dark, 5 minutes. Lets arousal fall back down.
- **Calm music** — slow tempo, low complexity (ambient, soft instrumental). Same lever as the energizing playlist, pointed the other way: slow music lowers heart rate and shifts you toward the rest-and-digest side. Use it to *settle* — do not reach for the energizing playlist here.
- **Long-exhale breathing** — physiological sigh (double inhale, slow long exhale) ×3. The fastest down-shift available.
- **Cold water on the FACE** — slows the heart. Calming; the opposite effect from a cold shower on the body.
- **Deep pressure** — heavy blanket, firm pressure.
- **10-minute yoga nidra (NSDR)** — guided non-sleep deep rest. Settles arousal AND restores energy — no sleep inertia, no disruption to tonight's sleep the way a nap has. Doubles as the Type D fatigue lever, usable any time of day.

**Mixed state — overwhelmed AND something must get done: settle first, activate second.** When you're over-aroused *but* something genuinely can't wait, you need both poles, in ORDER. Down-shift the stress spike first, THEN bring clean arousal up. **Never lead with a hard spike** (cold plunge, max sprint) while still flooded — it drives overload higher before you've settled.

1. **Settle (30–60s):** 3 physiological sighs + cold water on the FACE (not a body cold shower). Calm, slow music can run underneath; switch to the energizing playlist only at the activate step.
2. **Fuel if depleted:** a few bites, so the tank isn't empty.
3. **Activate gently:** music on, plus the act of getting moving (loading the car, carrying the thing) is usually enough — no separate burst needed.
4. **Fuller version (~8 min):** a warm shower with a 20–30s cold finish — relaxation then activation in one ritual.

The rule: **still the water, then light it.** Calm → rise, in sequence. Never simultaneously, never spike-first.

Both poles sit downstream of the **upstream gates** (sleep, food, movement). A lever buys a state change; it does not substitute for a missing gate.
