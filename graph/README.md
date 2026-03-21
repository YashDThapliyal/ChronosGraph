# graph/

Graph database interface layer.

---

## Purpose

Provides a **backend-agnostic API** for all graph read and write
operations.  The rest of the system interacts with the knowledge graph
exclusively through `GraphInterface` — it never calls Neo4j, NetworkX,
or any other library directly.

---

## What belongs here

- `graph_interface.py` — abstract `GraphInterface`
- Concrete graph backends (Phase 4+, e.g. `neo4j_graph.py`,
  `networkx_graph.py`, `stub_graph.py`)

---

## What does NOT belong here

- Business logic for deciding *what* to write (belongs in `core/`)
- Query construction for domain questions (belongs in `queries/`)
- Storage of events or beliefs as plain objects (belongs in `storage/`)

---

## Dependency Rules

`graph/` may import from:
- `config/` (for connection settings)
- Standard library + graph DB drivers (e.g. `neo4j`)

`graph/` must **NOT** import from:
- `simulator/`
- `ingestion/`
- `core/`

---

## How it connects

```
core/ implementations ──► graph/   (write nodes and edges on events)
queries/ ──────────────► graph/   (traverse graph for answers)
```
