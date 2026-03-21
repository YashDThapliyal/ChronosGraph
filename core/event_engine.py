"""
Event models and in-memory event engine for ChronosGraph Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from simulator.models import Position


@dataclass(frozen=True)
class Event:
    """Base immutable event."""

    timestamp: float
    subject_entity_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class MovedEvent(Event):
    """Entity moved beyond movement threshold."""

    old_position: Position = field(default_factory=lambda: Position(0.0, 0.0, 0.0))
    new_position: Position = field(default_factory=lambda: Position(0.0, 0.0, 0.0))
    distance: float = 0.0


@dataclass(frozen=True)
class VisibilityChangedEvent(Event):
    """Entity visibility changed."""

    old_visibility: bool = False
    new_visibility: bool = False


@dataclass(frozen=True)
class RelationshipChangedEvent(Event):
    """Entity parent receptacle changed."""

    old_parent: str | None = None
    new_parent: str | None = None


class EventEngine:
    """Stores detected events in memory."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def process_changes(self, events: list[Event]) -> None:
        """Append newly detected events."""
        self._events.extend(events)

    def get_all_events(self) -> list[Event]:
        """Return all processed events."""
        return list(self._events)
