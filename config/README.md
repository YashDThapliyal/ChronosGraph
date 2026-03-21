# config/

System-wide runtime configuration for ChronosGraph.

---

## Purpose

Centralise all tunable parameters — backend choices, debug flags, model
names, tick rates — in one typed dataclass so every other module receives
a consistent `ChronosGraphSettings` object instead of scattered
environment variables or magic constants.

---

## What belongs here

- `settings.py` — the `ChronosGraphSettings` dataclass
- Future: environment-variable loaders (e.g. `from_env()`)
- Future: YAML / TOML config file parsers

---

## What does NOT belong here

- Business logic of any kind
- Module-specific constants (keep those near their module)
- Secrets or credentials (use environment variables / vaults)

---

## How it connects

`main.py` and any module that needs runtime parameters imports
`ChronosGraphSettings` from here.  No other module should be imported
by `config/`.
