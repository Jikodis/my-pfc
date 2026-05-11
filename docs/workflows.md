# Workflows

Visual documentation of how the productivity system works. Diagrams use Mermaid syntax.

## System Flow — Values to Actions

```mermaid
flowchart TD
    V[Values] --> AS[Area Statements]
    V --> PB[Passion Brainstorm]
    V --> Q[Questions]
    AS --> P[Projects]
    PB --> P
    P --> T[Tasks]
    AS --> H[Habits]
    P --> H
    T --> DF[Daily Focus 2+1]
```

## Daily Flow

```mermaid
flowchart TD
    A[Morning Check-in] --> B[Review email priorities]
    B --> C[Set daily focus: 2 critical + 1 bonus]
    C --> D[Work on focus tasks]
    D --> E[Log habits as completed]
    E --> F[End of day: rate day 1-5 + notes]
    F --> G[Commit and push]
```

## Weekly Review Flow

```mermaid
flowchart TD
    A[Gather data: tasks, habits, check-ins, focus] --> B[Summarize the week]
    B --> C[Stale task triage]
    C --> D{Task open 2+ weeks?}
    D -->|Eliminate| E[Remove task]
    D -->|Break down| F[Split into smaller parts]
    D -->|Keep| G[Re-prioritize]
    B --> H[Archive completed tasks]
    H --> I[Ask: what went well / what didn't]
    I --> J[Commit and push]
```

## Monthly Check-in Flow

```mermaid
flowchart TD
    A[Life wheel assessment] --> B[Household status assessment]
    B --> C[Project progress review]
    C --> D{Anything not green?}
    D -->|Yes| E[Create habit, action, or project]
    D -->|No| F[Continue as-is]
    C --> G{Project stalled?}
    G -->|Yes| H[Pause/swap/break down further]
    G -->|No| I[Update percentage]
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
