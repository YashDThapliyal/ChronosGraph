# ingestion/

Observation ingestion and translation layer.

---

## Purpose

Acts as the **seam between the simulator and the memory system**.
Raw `Observation` objects arrive from the simulator; this module
validates, normalises, and forwards them into `core/` as structured
data.

---

## What belongs here

- `observation_processor.py` — abstract `ObservationProcessor`
- Concrete processors (Phase 1+, e.g. `standard_processor.py`)
- Validation and normalisation helpers

---

## What does NOT belong here

- Simulator implementation code (belongs in `simulator/`)
- Persistence / storage logic (belongs in `storage/`)
- Graph writes (belongs in `graph/`)
- Business rules about what events mean (belongs in `core/`)

---

## How it connects

```
simulator/ ──► ingestion/ ──► core/
```

`ingestion/` is the **only** module allowed to import from both
`simulator/` and `core/`.  It calls `EntityManagerInterface` and
`EventEngineInterface` from `core/` — never the other way around.
