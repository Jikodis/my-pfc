# Workflows

Visual documentation of how the productivity system works. Diagrams use Mermaid syntax.

## System Flow — Values to Tasks

```mermaid
flowchart TD
    V[Values] --> AS[Area Statements]
    V --> PB[Vision Brainstorm]
    V --> Q[Questions]
    AS --> P[Projects]
    PB --> P
    P --> T[Tasks]
    AS --> H[Habits]
    P --> H
    T --> DF[Daily Focus 2+1]
```

## Daily Flow — the tour, any time

```mermaid
flowchart TD
    A[Walk me through on the home page] --> B[Rate a day: yesterday before 6 PM, today after]
    B --> C[Body check: sleep, exercise, habit ticks]
    C --> E[What needs you: urgent items, else at most 1 due review]
    E --> F[Set the 2+1: rest of today, tomorrow's after 6 PM]
    F --> G[Why: one focus and its vision]
```

Each answer is saved and pushed by `automations/scripts/web_write.py` the moment it is given.

## Rolling Reviews Flow

The old weekly and monthly ritual reviews are folded into a rolling ledger (`data/review-ledger.ndjson`). The tour shows at most 1 due item; `/pfc-review` clears the whole backlog at once.

```mermaid
flowchart TD
    A[Ledger: review items, each with cadence + last_done] --> B{Any item due AND has something to act on?}
    B -->|No| C[No review today — re-check next time]
    B -->|Yes| D[Take the most-overdue, gated items]
    D --> E[Tour: cap 1 · /pfc-review: no cap]
    E --> F[Point at the owning skill: /pfc-revive, /pfc-focus, life-wheel, /pfc-insights, ...]
    F --> G{User engages?}
    G -->|Yes| H[Stamp last_done = today]
    G -->|No| I[Leave it — re-surfaces on cadence]
```

## Hypothesis Testing Flow

```mermaid
flowchart TD
    A[Observe pattern in day tracking] --> B[Form hypothesis]
    B --> C[Design simple test]
    C --> D[Track for 1-2 weeks]
    D --> E[Analyze results]
    E --> F{Confirmed?}
    F -->|Yes| G[Document finding, adjust habits]
    F -->|No| H[Document finding, try new hypothesis]
```
