"""ChronosGraph entry point for demo + world-state queries."""

from chronosgraph.bootstrap import bootstrap_world
from world.world_state_engine import WorldStateEngine


def _print_world_queries(world_engine: WorldStateEngine) -> None:
    """Print simple world-state queries for the key entity."""
    print("\n=== WORLD STATE QUERIES ===")
    print("Current parent of keys_001:", world_engine.get_current_parent("keys_001"))
    print("Parent of keys_001 at t=0.30:", world_engine.get_parent_at("keys_001", 0.30))
    print("History length:", len(world_engine.get_event_history("keys_001")))


def main() -> None:
    """Run demo bootstrap and print world-state query results."""
    try:
        world_engine = bootstrap_world(demo=True)
    except RuntimeError as exc:
        print(f"Simulator initialization failed: {exc}")
        return

    _print_world_queries(world_engine)


if __name__ == "__main__":
    main()
