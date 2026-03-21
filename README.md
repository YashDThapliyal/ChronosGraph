# ChronosGraph

A modular, embodied memory system that tracks, stores, and reasons over
entity state changes across time — built as a temporal knowledge graph.

---

## Project Vision

ChronosGraph ingests observations from a world simulator, detects meaningful
changes in entity state, emits structured events, updates a temporal knowledge
graph, and exposes a query interface for reconstructing history or current
beliefs at any point in time.

---

## Architecture Overview

```
simulator/ ──► ingestion/ ──► core/ ──► storage/
                                 └──► graph/
                                        ▲
                               queries/ ┘
```

| Layer        | Responsibility                                      |
|--------------|-----------------------------------------------------|
| `simulator/` | World simulation interface and raw data models      |
| `ingestion/` | Transforms raw observations into core-ready data    |
| `core/`      | Change detection, event emission, belief management |
| `storage/`   | Persistence interfaces for events, entities, beliefs|
| `graph/`     | Graph database interface (e.g. Neo4j)               |
| `queries/`   | High-level query interface over the knowledge graph |
| `config/`    | System-wide configuration                           |

---

## Dependency Rules

- `core/` must **NOT** import from `simulator/`
- `storage/` must **NOT** import from `simulator/`
- `simulator/` must **NOT** depend on memory logic
- All cross-module interactions must go through **abstract interfaces**
- No circular imports

---

## Development Phases

| Phase | Description                          | Status      |
|-------|--------------------------------------|-------------|
| 0     | Skeleton, interfaces, dataclasses    | In Progress |
| 1     | In-memory simulator + ingestion      | Pending     |
| 2     | Core event engine + change detector  | Pending     |
| 3     | Storage implementations              | Pending     |
| 4     | Neo4j graph integration              | Pending     |
| 5     | LLM-based reasoning layer            | Pending     |
| 6     | Query API and UI                     | Pending     |

---

## Requirements

- Python 3.10+
- No heavy dependencies in Phase 0

---

## Quickstart

```bash
python main.py
```

## Running Phase 2 Demo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
