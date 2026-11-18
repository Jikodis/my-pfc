# Agents — data folder

Folder-scoped operational rules for any agent reading or writing in `data/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `insights.ndjson` | One insight per line | Mutable (status can change to `graduated`, `archived`) |
| `hypotheses.ndjson` | One hypothesis per line | Mutable (status, last_reviewed) |
| `findings.ndjson` | One finding per line | Mutable but rare |
| `day-tracking.ndjson` | One entry per day | Append for new day; mutable in place during the day |
| `supplements.ndjson` | One supplement entry per line | Mutable for stop-date; new doses are new records, never edits to `dose` |
| `grounding.ndjson` | One Front-of-Mind topic per line | Mutable (status → `retired`, `retired_date`) |
| `review-ledger.ndjson` | One rolling-review item per line | Mutable (`last_done` stamped on engagement) |
| `revive-events.ndjson` | One revive intervention per line | Append; `outcome` updated in place later |
| `ai-news.ndjson` | One blog post per line: `{url, source, title, published, decided, decision: keep\|skip\|null, reason, status: done\|skipped\|failed, partial, epub, mp3, seconds, mp3_error}` | Append only, by `automations/scripts/ai_news.py` (daily timer). See `docs/ai-news.md` |
| `health-raw/` | One gzipped JSON per day | Written by the health fetch; not NDJSON, not validated |
| `.jq_update.tmp` | Temp file | Should NEVER persist between operations |

Schemas: `config/{insight,hypothesis,finding,supplement,grounding,review_ledger,revive_event}_schema.yaml`.

## Front of Mind (`grounding.ndjson`)

A small, cycling set of "keep this front-of-mind right now" anchors, rendered to the Trello `🧠 Front of mind` list. The bar is **critical, present-tense importance** — genuinely load-bearing stuff, not trivia or reference. Distinct from an insight (a noticing to triage) and a finding (a proven conclusion). One record per **topic** (title + bulleted body), soft cap 10 active — curate by retiring, never delete.

## Three stores, in order of bar

- **Insights** (`insights.ndjson`) — personal observations / noticings / revelations. Captured freely throughout the week via `/pfc-add-insight`. Lower bar than a finding. Reviewed via the `insights-review` rolling review or on demand via `/pfc-insights`. May graduate into a task, project, or habit (status → `graduated`, `graduated_to` set).
- **Hypotheses** (`hypotheses.ndjson`) — experiments to run. Track patterns to test against data.
- **Findings** (`findings.ndjson`) — durable, hard-won insights. Added rarely. A hypothesis graduates to a finding when supporting data meets the bar: n ≥ 30, |r| ≥ 0.3, p < 0.01. Findings may also be added manually from life experience (`source: "experience"`).

## Hard rules

1. **All structured writes go through `jq`.** Same rule as everywhere else.
2. **Supplement dose changes are stop + add, never in-place edits to `dose`.** A supplement is "active on date D" iff `started <= D AND (stopped is null OR stopped > D)` — `started` inclusive, `stopped` exclusive. Editing `dose` in place corrupts the longitudinal record.
3. **Findings have a high graduation bar.** When promoting a hypothesis to finding: n ≥ 30 observations, |r| ≥ 0.3, p < 0.01 if statistical, or clear lived-experience pattern if `source: "experience"`. Surface the bar; don't graduate quietly.
4. **`.jq_update.tmp` is the atomic-update staging file.** Always use `... > data/.jq_update.tmp && mv data/.jq_update.tmp <target>`. The temp file should not be checked into git; `.gitignore` should cover it.
5. **Date stamps in `$LOCAL_TZ`** for everything: `created`, `graduated_date`, `started`, `stopped`, `last_reviewed`.

## Canonical query patterns

```bash
# Active supplements on a given date
TARGET="2026-05-11"
jq -c --arg d "$TARGET" \
  'select(.started <= $d and (.stopped == null or .stopped > $d))' \
  data/supplements.ndjson

# Insights still in `active` status
jq -c 'select(.status == "active")' data/insights.ndjson

# Days in the last 30 with rating >= 4
SINCE=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '30 days ago' '+%Y-%m-%d')
jq -c --arg s "$SINCE" 'select(.date >= $s and .rating >= 4)' data/day-tracking.ndjson
```

## Insight → hypothesis → finding graduation

When an insight is promoted to a hypothesis, **don't delete the insight** — mutate it to `status: "graduated"` and add `graduated_to: "<hypothesis-id>"`. Same when a hypothesis graduates to a finding. The ladder is preserved as a chain, not destroyed.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Hypotheses, insights, and findings.
- [`docs/data-model.md`](../docs/data-model.md) — full schemas.
