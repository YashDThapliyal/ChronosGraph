"""
Abstract interface for persistent event storage.

The EventStore is the append-only log of every Event ever emitted by the
core system.  It is the primary source of truth for temporal queries.
"""

from abc import ABC, abstractmethod
from typing import Optional

from core.event_engine import Event


class EventStoreInterface(ABC):
    """
    Defines the contract for durable event persistence.

    Implementations may back this with an in-memory list, SQLite,
    a time-series database, or Neo4j node sequences.
    """

    @abstractmethod
    def save_event(self, event: Event) -> None:
        """
        Persist an event.

        Args:
            event: The event to store.  Must have a unique `event_id`.
        """
        ...

    @abstractmethod
    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """
        Retrieve a single event by its unique ID.

        Args:
            event_id: The event's unique identifier.

        Returns:
            The matching event, or None if not found.
        """
        ...

    @abstractmethod
    def get_events(
        self,
        event_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[Event]:
        """
        Retrieve events matching the given criteria.

        All filters are combined with AND semantics.  Omitting a filter
        means "no restriction on that field".

        Args:
            event_type:       Filter by event type string.
            source_entity_id: Filter by the entity that caused the event.
            since:            Include only events at or after this timestamp.
            until:            Include only events at or before this timestamp.
            limit:            Maximum number of events to return.

        Returns:
            A list of matching events ordered by timestamp ascending.
        """
        ...

    @abstractmethod
    def count_events(
        self,
        event_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
    ) -> int:
        """
        Count events matching the given criteria without loading them.

        Args:
            event_type:       Optional filter by event type.
            source_entity_id: Optional filter by source entity.

        Returns:
            Number of matching events.
        """
        ...
