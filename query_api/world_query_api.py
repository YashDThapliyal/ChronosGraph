"""World-memory query adapter for MCP tools."""

from __future__ import annotations

from simulator.models import Position
from world.world_state_engine import StateSnapshot, WorldStateEngine


class WorldQueryAPI:
    """JSON-serializable read-only adapter over WorldStateEngine."""

    def __init__(self, world_engine: WorldStateEngine) -> None:
        self._world_engine = world_engine

    def where_is(self, entity_id: str) -> dict[str, str | None]:
        """Return current parent location for an entity."""
        return {
            "entity_id": entity_id,
            "parent": self._world_engine.get_current_parent(entity_id),
        }

    def where_was(self, entity_id: str, timestamp: float) -> dict[str, str | None | float]:
        """Return parent location for an entity at a timestamp."""
        return {
            "entity_id": entity_id,
            "timestamp": float(timestamp),
            "parent": self._world_engine.get_parent_at(entity_id, float(timestamp)),
        }

    def what_happened(self, entity_id: str) -> list[dict[str, object]]:
        """Return full state history for an entity."""
        history = self._world_engine.get_event_history(entity_id)
        return [self._snapshot_to_dict(snapshot) for snapshot in history]

    def _snapshot_to_dict(self, snapshot: StateSnapshot) -> dict[str, object]:
        return {
            "timestamp": snapshot.timestamp,
            "parent": snapshot.parent,
            "position": self._position_to_dict(snapshot.position),
            "visible": snapshot.visible,
        }

    @staticmethod
    def _position_to_dict(position: Position | None) -> dict[str, float] | None:
        if position is None:
            return None
        return {"x": position.x, "y": position.y, "z": position.z}
