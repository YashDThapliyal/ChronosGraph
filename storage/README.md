# storage/

Persistence interfaces for events, entity snapshots, and beliefs.

---

## Purpose

Defines **how** ChronosGraph durably stores the three fundamental data
types it manages: events (what happened), entity snapshots (what things
looked like), and beliefs (what the system believes to be true).

This layer only holds **interfaces**.  Concrete implementations
(in-memory, SQLite, Neo4j) are added in later phases.

---

## What belongs here

| File               | Interface                | Stores                            |
|--------------------|--------------------------|-----------------------------------|
| `event_store.py`   | `EventStoreInterface`    | All emitted `Event` objects       |
| `entity_store.py`  | `EntityStoreInterface`   | Point-in-time entity snapshots    |
| `belief_store.py`  | `BeliefStoreInterface`   | Active and historical `Belief`s   |

---

## What does NOT belong here

- Simulator code or raw observation models
- Change detection or event generation logic (belongs in `core/`)
- Graph traversal queries (belongs in `graph/`)
- Business reasoning (belongs in `core/`)

---

## Dependency Rules

`storage/` may import from:
- `core/` (for `Event` and `Belief` dataclasses)
- `config/` (for backend connection settings)
- Standard library

`storage/` must **NOT** import from:
- `simulator/`
- `ingestion/`
- `graph/`

---

## How it connects

```
core/ ──► storage/
graph/ ──► storage/   (graph implementations may delegate to stores)
queries/ ──► storage/ (query layer reads from stores)
```
