# Workflows

Visual documentation of how the productivity system works. Diagrams use Mermaid syntax.

## System Flow — Values to Actions

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

## Daily Flow — the evening spine

```mermaid
flowchart TD
    A[Evening Check-in] --> B[Rate + log today: energy, focus, mood, habits]
    B --> C[Rolling reviews: surface up to 2 due items]
    C --> D[Trickle Current Focus into view]
    D --> E[Pick tomorrow's 2+1 + annotate anchor slot]
    E --> F[Commit and push]
```

## Rolling Reviews Flow

The old weekly and monthly ritual reviews are folded into a rolling ledger (`data/review-ledger.ndjson`). The evening check-in drips ≤2 due items per night; `/pfc-review` clears the whole backlog at once.

```mermaid
flowchart TD
    A[Ledger: review items, each with cadence + last_done] --> B{Any item due AND has something to act on?}
    B -->|No| C[No reviews tonight — re-check next evening]
    B -->|Yes| D[Take the most-overdue, gated items]
    D --> E[Evening: cap 2 · /pfc-review: no cap]
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
