# simulator/

World simulation interface and raw observation data models.

---

## Purpose

Defines **what the world looks like** from the perspective of a sensor or
observer.  Concrete simulator implementations live here (in later phases)
and expose their output through `SimulatorInterface`.

---

## What belongs here

- `simulator_interface.py` — abstract `SimulatorInterface` (tick, reset, …)
- `models.py` — raw data classes: `Position`, `EntityObservation`, `Observation`
- Concrete simulator implementations (Phase 1+, e.g. `grid_world.py`)

---

## What does NOT belong here

- Memory logic (event detection, beliefs, graph writes)
- Storage or persistence code
- LLM or reasoning code
- Anything from `core/`, `storage/`, or `graph/`

---

## How it connects

```
simulator/ ──► ingestion/
```

`SimulatorInterface.step()` returns an `Observation`.
The `ingestion/` layer consumes that observation and passes processed
data into `core/`.  No other module imports from `simulator/` directly.
