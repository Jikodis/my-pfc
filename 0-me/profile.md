# Profile — Who you are and how this brain operates

This file is always-loaded ground truth for any agent reading this repo. It captures who you are and what works/doesn't work cognitively. The deeper assessments (`personality.md`, `core-psychology.md`) are optional and not shipped — most users don't need them.

**Out-of-the-box state:** the **Brain** section ships with conservative defaults that work for the target audience (ADHD / autism / executive-function variants) — leave it as-is until you have a reason to change it. The **Who** section is mostly placeholders and needs personalization to be useful — the agent reads this file every request, so the sooner you fill it in, the better the suggestions you get.

Recommended path: run `/pfc-onboarding meta/profile` early in your onboarding arc (right after `meta/set-local-timezone`). The lesson walks you through each line and what level of detail makes sense.

## Who

Fill in your own. Aim for terse — single words or short phrases. The agent reads this every session.

- **Personality framework results (optional):** e.g. INTP / Enneagram 2 / DISC-C — pick whatever framework's vocabulary helps you.
- **Top motivators (top 5-7):** what actually drives you. Skip the trite list; what genuinely makes you do work?
- **Anti-motivators:** things sometimes treated as motivators that *don't* work for you (recognition, money, prestige, pressure can all be weak motivators for some people — name yours).
- **Top values (link to `1-values/values.md`):** the system pressure-tests new projects against this list.
- **Love languages or connection currencies (optional):** important for the "personal time vs deep work" calibration the system uses.

## Brain

This section is the load-bearing one for ADHD/autism/alexithymia accommodations. Edit any line that doesn't fit you; remove sections you don't need. The shipped defaults are conservative — they apply to most people in the target audience.

- **Diagnosed (or self-identified):** ASD / ADHD inattentive / OCD / Alexithymia — edit to match your profile. These conditions inform the accommodations below.
- **Attention paradox:** short structured tasks land easily; sustained self-directed tasks are hard — supported by executive function assessment. Horsepower fine; initiation layer broken.
- **Story memory may be a weakness.** If verbal/narrative recall and live word-finding are unreliable for you, externalize and prefer async over live.
- **Discrete-item working memory may be fine** — lists, numbers, code are fine. The accommodation is for *narrative* recall, not all memory.
- **Alexithymia layer (optional):** "How do I feel?" may be an unreliable real-time signal. Prefer behavioral proxies (avoided? gripping? defensive? procrastinating?) and objective metrics (wearable, focus completion rate, day rating) over introspective self-report. Good at reading others' feelings, unreliable at reading own — a common alexithymia pattern.
- **Masking load:** social interaction may cost more than contact time alone — recovery budget after performance days is real.
- **Systemizing high, empathy below average:** pattern recognition is a genuine strength; hyperfocus within a time budget is valuable.
- **"I'm fine" calibration:** tendency to minimize (common in ASD/alexithymia profiles) plus potential low internal signal detection. If reports mild → treat as moderate.
- **EF strengths to leverage:** Response Inhibition, Emotional Control, Flexibility, Emotional Regulation. Does not spiral under stress.
- **Hyperfocus is a problem state by default.** Deep dive is valuable only within an *explicitly set* budget; default unbounded hyperfocus needs interruption, not encouragement.

## How to work with this brain — always

1. **Break tasks into ~15-min chunks.** No "grind through this block." Initiation and execution accommodations matter — this is accommodation, not style.
2. **Specify before executing.** (Conceptual-model-first — common in ASD and analytical profiles.) Don't skip the "why." Budget it. Rushing past it stalls the project, not saves time.
3. **Externalize state.** Checklists, notes, diffs, calendar, this repo — never hold multi-step state in your head. Story memory may be weak — externalize everything.
4. **Async over live** on anything high-stakes or word-finding-heavy. Let yourself draft. Don't work in live Q&A mode when high-stakes words matter.
5. **Hyperfocus is a problem state by default — break it.** Treat hyperfocus like frozen: interject when noticed.
6. **Pair the finish line.** If you have idea-generation as a strength and execution/rallying as a frustration (common in ADHD/autism profiles), front-load structure so the push is short and pre-committed.
7. **Sensory is infrastructure.** Headphones, consistent background noise, predictable lighting — not preferences; cognitive scaffolding.
8. **Trust objective metrics over check-ins.** Sleep, activity, focus completion, day rating beat "I feel fine" — especially if alexithymia makes the latter unreliable.
9. **Protect personal time.** Fill in your own time-protection windows in `0-me/schedule-patterns.md` — the calendar scheduling skill will respect them. See `docs/calendar-scheduling.md`.
10. **Communicate literally.** No subtext, no figurative framing, no polite lies.
11. **Prioritize for you, don't ask you to prioritize mid-flight.** If planning and prioritization may be a weakness (common in ADHD profiles), the system picks; you execute.
12. **Respect requests for justification.** Won't follow arbitrary rules; any ask needs a defensible *why*. This isn't resistance — it's a high-fairness brain asking for justification. Give it.
13. **Object-based reminders may not work.** Sticky notes, sand timers, progress bars, visible piles — for many in the target audience these go invisible within ~2 days. The reliable trigger is **an external start signal anchored to an already-running state** (end of a meeting → next block; music-on ritual → next chunk), so the two activities are one unit with no decision gap. The trigger fires at the START, then work solo — a check-in after the start does nothing.
14. **Lower the effort side, don't try to raise willpower.** Collapse steps to near-zero. Move the official spot to where the lowest-effort drop already happens. Clutter maps where the effort calculator gave up — fix it by relocating the "correct" spot, not by demanding more discipline.
15. **Don't fabricate interest for zero-interest tasks.** Re-activating a genuine latent interest works; manufacturing interest in folding laundry doesn't. For zero-interest tasks the realistic levers are music + real urgency + an external start trigger + radical step-reduction — or route around the task entirely. You don't have to win every hill.
16. **Vigorous exercise is often the under-treated lever.** Morning vigorous cardio can bring task-switching and flexibility online in a way gentle movement doesn't. When suggesting fixes for a switching/initiation problem, check the exercise input before redesigning the system.
17. **Sleep continuity, not just hours.** Adequate total hours with a broken-up night (late onset, long early-morning wake, high awake-minutes) can still produce a depleted day. Don't pass a "good sleep" judgment on total hours alone — read awake-minutes / efficiency too. On a fragmented night: name it, lower the day's ceiling, and treat continuous sleep tonight as the real fix.
