# queries/

High-level domain query interface for ChronosGraph.

---

## Purpose

Exposes **user-facing questions** about the knowledge graph in a
backend-agnostic way.  Callers ask things like "what happened to entity X
between T1 and T2?" without needing to know whether the answer comes from
Neo4j, an in-memory store, or a combination of both.

---

## What belongs here

- `query_interface.py` — abstract `QueryInterface` + `QueryResult`
- Concrete query implementations (Phase 4+, e.g. `neo4j_query.py`,
  `in_memory_query.py`)
- Composable query builder helpers (future)

---

## What does NOT belong here

- Graph writes or mutations (belongs in `graph/` or `core/`)
- Business logic that decides what events mean (belongs in `core/`)
- Raw Cypher query templates (belongs in concrete implementations)

---

## Dependency Rules

`queries/` may import from:
- `graph/` (to traverse the graph)
- `storage/` (to read events, snapshots, and beliefs)
- `config/` (for settings)

`queries/` must **NOT** import from:
- `simulator/`
- `ingestion/`
- `core/` (except dataclasses like `Event` and `Belief`)

---

## How it connects

```
client code ──► queries/ ──► graph/
                         └──► storage/
```
