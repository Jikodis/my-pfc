---
name: pfc-stuck
description: Break out of frozen, locked-in, foggy, or fatigue states. Use when the user says "stuck", "frozen", "can't start", "can't stop", "locked in", "nothing is clicking", "tired", or "not functional".
---

# Stuck Protocol

When invoked, diagnose the type of stuck first, then deliver the right intervention. Do NOT dump all four types at once — ask one question, get the answer, act.

## Step 1: Diagnose

Ask exactly:

> "Which fits right now?
> A — Can't start (frozen, spinning, avoiding)
> B — Can't stop (locked into one thing, ignoring everything else)
> C — Foggy / low energy (partially functional, nothing clicking)
> D — Physically tired (heavy eyelids, body wants rest)"

If the user already named the type in their message, skip to Step 2.

## Step 2: Intervene by type

When the user rationalizes the suggestion away — hold the line.

State the position once:

> "This method works for you. You have permission to do it without overthinking. Body-state change comes first — the cognitive work goes better after, not before."

Don't argue or escalate. State the position once and hold it.

### TYPE A — FROZEN (can't start)

**First:** put on energizing music. Don't negotiate; just press play.

**Second:** while music plays, pick the smallest clearly-defined task — something with a specific output you can finish in 5-15 minutes.

```bash
grep '"status":"open"' 5-actions/_data/tasks.ndjson | python3 -c "
import sys, json
tasks = [json.loads(l) for l in sys.stdin if l.strip()]
small = [t for t in tasks if t.get('size') in ('XS','S')]
small.sort(key=lambda t: {'XS':0,'S':1}.get(t.get('size','S'),2))
for t in small[:3]: print(f\"[{t['size']}] {t['id']}: {t['description']}\")
"
```

### TYPE B — LOCKED IN (can't stop)

Hyperfocus is a problem state by default. Break it.

1. **Stop the screen.** Stand up. Walk away from the device for 5 minutes.
2. **Re-orient.** Read the day's 2+1 from `5-actions/_data/daily-focus.ndjson`. Is the current focus item actually one of them? If not, you're off-plan.
3. **Pick one of the day's 2+1** and switch to it for 30 minutes minimum before returning to the previous task.

### TYPE C — FOGGY (low energy)

Diagnose inputs first:
- Sleep — check `data/day-tracking.ndjson` last row's `health.sleep_hours`. <7 hours? Fog explained.
- Food — eaten in the last 4 hours?
- Hydration — water in the last hour?

If any input is missing, fix it first. If all three are healthy, do a 5-minute physical reset (walk, light stretching, anything that gets blood moving).

### TYPE D — TIRED (physical fatigue)

Power nap. 20 minutes, alarm set, no longer. The cognitive recovery is real and well-documented; pushing through tired produces low-quality work and damages the next day.

After the nap: 5 minutes of light movement before returning to work.
