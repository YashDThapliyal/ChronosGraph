"""In-memory temporal world model driven by emitted events."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.event_engine import (
    Event,
    MovedEvent,
    RelationshipChangedEvent,
    VisibilityChangedEvent,
)
from simulator.models import Observation, Position


@dataclass
class StateSnapshot:
    """Point-in-time snapshot of tracked entity state."""

    timestamp: float
    parent: str | None
    position: Position | None
    visible: bool


@dataclass
class EntityState:
    """Mutable current state plus chronological history."""

    entity_id: str
    current_parent: str | None = None
    current_position: Position | None = None
    visible: bool = False
    history: list[StateSnapshot] = field(default_factory=list)


class WorldStateEngine:
    """Consumes events and maintains an in-memory temporal world model."""

    def __init__(self) -> None:
        self._entities: dict[str, EntityState] = {}

    @property
    def entities(self) -> dict[str, EntityState]:
        """All tracked entities (entity_id -> state)."""
        return self._entities

    def seed_from_observation(self, observation: Observation) -> None:
        """Initialize world state from first observation snapshot."""
        for entity in observation.entities:
            state = EntityState(
                entity_id=entity.entity_id,
                current_parent=entity.parent_receptacle,
                current_position=entity.position,
                visible=entity.visible,
                history=[]
            )

            state.history.append(
                StateSnapshot(
                    timestamp=observation.timestamp,
                    parent=entity.parent_receptacle,
                    position=entity.position,
                    visible=entity.visible,
                )
            )

            self._entities[entity.entity_id] = state

    def process_event(self, event: Event) -> None:
        """Apply one event to current state and append a snapshot."""
        entity = self._entities.get(event.subject_entity_id)
        if entity is None:
            entity = EntityState(entity_id=event.subject_entity_id)
            self._entities[event.subject_entity_id] = entity

        if isinstance(event, MovedEvent):
            entity.current_position = event.new_position
        elif isinstance(event, RelationshipChangedEvent):
            entity.current_parent = event.new_parent
        elif isinstance(event, VisibilityChangedEvent):
            entity.visible = event.new_visibility
        else:
            return

        entity.history.append(
            StateSnapshot(
                timestamp=event.timestamp,
                parent=entity.current_parent,
                position=entity.current_position,
                visible=entity.visible,
            )
        )

    def get_current_parent(self, entity_id: str) -> str | None:
        """Return current parent receptacle for an entity."""
        entity = self._entities.get(entity_id)
        if entity is None:
            return None
        return entity.current_parent

    def get_parent_at(self, entity_id: str, timestamp: float) -> str | None:
        """Return the latest known parent at or before the provided timestamp."""
        entity = self._entities.get(entity_id)
        if entity is None:
            return None

        parent_at_time: str | None = None
        for snapshot in entity.history:
            if snapshot.timestamp <= timestamp:
                parent_at_time = snapshot.parent
            else:
                break
        return parent_at_time

    def get_event_history(self, entity_id: str) -> list[StateSnapshot]:
        """Return chronological state snapshots for an entity."""
        entity = self._entities.get(entity_id)
        if entity is None:
            return []
        return list(entity.history)
