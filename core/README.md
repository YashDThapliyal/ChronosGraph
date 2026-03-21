# core/

The memory and reasoning nucleus of ChronosGraph.

---

## Purpose

Defines the interfaces and data structures that make ChronosGraph a
*temporal knowledge system* rather than a plain event logger.  The core
layer detects meaningful changes, emits typed events, tracks entity
state, and manages higher-level beliefs.

---

## What belongs here

| File                   | Responsibility                                         |
|------------------------|--------------------------------------------------------|
| `event_engine.py`      | `Event` dataclass + `EventEngineInterface`             |
| `entity_manager.py`    | `EntityManagerInterface` — current entity state CRUD   |
| `change_detector.py`   | `ChangeDetectorInterface` — diff two entity snapshots  |
| `belief_manager.py`    | `Belief` dataclass + `BeliefManagerInterface`          |

---

## What does NOT belong here

- Simulator code or raw observation models (belongs in `simulator/`)
- Ingestion / translation logic (belongs in `ingestion/`)
- Persistence implementations (belongs in `storage/`)
- Graph database queries (belongs in `graph/`)

---

## Dependency Rules

`core/` must **NOT** import from:
- `simulator/`
- `ingestion/`
- `storage/`
- `graph/`

`core/` may import from:
- `config/` (for settings)
- Standard library only

---

## How it connects

```
ingestion/ ──► core/ ──► storage/
                    └──► graph/
```

`ingestion/` feeds processed observations into `core/` via
`EntityManagerInterface` and `EventEngineInterface`.
`storage/` and `graph/` subscribe to events or are called by core
implementations to persist state.
