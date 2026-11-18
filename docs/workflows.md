# Workflows

Visual documentation of how the productivity system works. Diagrams use Mermaid syntax.

## System Flow — Values to Tasks

The layers follow the VAVFPTH model (Values, Areas, Visions, Focus, Projects, Tasks, Habits). Links between layers are optional except Focus to Habits: every active focus names its vehicle habits.

```mermaid
flowchart TD
    V[Values] --> AS[Areas + area statements]
    V --> Q[Questions]
    V --> PB[Vision Brainstorm]
    PB --> VI[Visions]
    AS --> VI
    VI --> F[Current Focus]
    AS --> F
    F --> H[Habits: vehicle habits]
    F --> P[Projects]
    PB --> P
    P --> T[Tasks]
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

The optional web home page, the Trello board and the reMarkable pages run parts of the same loop with buttons, ticks or ink (rate the day, log habits, set the 2+1, answer the due review). They write the same files, so anything already done there is not asked again in the check-in.

## Rolling Reviews Flow

The old weekly and monthly ritual reviews are folded into a rolling ledger (`data/review-ledger.ndjson`). The evening check-in drips ≤2 due items per night. `/pfc-review`, the web UI's `/review` page and the reMarkable `4 - Review` page each show one due review at a time as a short form, picked by `automations/scripts/review_forms.py`; say "next" in chat to clear a backlog.

```mermaid
flowchart TD
    A[Ledger: review items, each with cadence + last_done] --> B{Any item due AND has something to act on?}
    B -->|No| C[No review now: re-check later]
    B -->|Yes| D[Pick one: never done first, then most overdue]
    D --> E[Show it as a form: chat, /review page, or reMarkable page]
    E --> G{What does the user do?}
    G -->|Answers| H[Apply the answers, stamp last_done = today, offer the next]
    G -->|Skip this review| J[Stamp last_done = today, no other writes]
    G -->|Walks away| I[Not stamped: it stays due]
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
