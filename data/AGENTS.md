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
| `.jq_update.tmp` | Temp file | Should NEVER persist between operations |

Schemas: `config/{insight,hypothesis,finding,supplement}_schema.yaml`.

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
