"""
System-wide configuration for ChronosGraph.

All runtime settings are defined here as a single dataclass so that
components receive a typed config object rather than raw environment
variables or magic strings.
"""

from dataclasses import dataclass

MOVEMENT_THRESHOLD = 0.05

@dataclass
class ChronosGraphSettings:
    """
    Top-level configuration for the ChronosGraph system.

    Fields are intentionally kept minimal for Phase 0 and will be extended
    as each subsystem is implemented in later phases.
    """

    project_name: str = "ChronosGraph"
    version: str = "0.1.0"
    debug: bool = False

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #
    # Supported values: "in_memory" | "sqlite" | "neo4j"
    storage_backend: str = "in_memory"

    # ------------------------------------------------------------------ #
    # Graph
    # ------------------------------------------------------------------ #
    # Supported values: "stub" | "neo4j"
    graph_backend: str = "stub"

    # ------------------------------------------------------------------ #
    # Neo4j connection
    # ------------------------------------------------------------------ #
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    use_neo4j: bool = False

    # ------------------------------------------------------------------ #
    # LLM (reserved for Phase 5+)
    # ------------------------------------------------------------------ #
    llm_enabled: bool = False
    llm_model: str = "claude-sonnet-4-6"

    # ------------------------------------------------------------------ #
    # Simulation
    # ------------------------------------------------------------------ #
    simulation_tick_rate: float = 1.0  # seconds per tick
    max_simulation_steps: int = 1000
    movement_threshold: float = MOVEMENT_THRESHOLD
