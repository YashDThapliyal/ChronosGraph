"""
High-level query interface over the ChronosGraph knowledge base.

QueryInterface expresses domain queries in terms that callers understand
(entities, time ranges, beliefs) and hides the complexity of graph
traversal, store lookups, and result assembly behind a clean API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class QueryResult:
    """
    Container returned by every query method.

    Attributes:
        success:  True if the query completed without error.
        data:     List of result records.  Each record is a plain dict
                  whose keys depend on the specific query.
        error:    Human-readable error message, populated only when
                  `success` is False.
        metadata: Optional context about the query execution
                  (e.g. elapsed time, backend used, result count).
    """

    success: bool
    data: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryInterface(ABC):
    """
    Defines high-level domain queries over the ChronosGraph system.

    Implementations will delegate to `GraphInterface`, `EventStoreInterface`,
    and `BeliefStoreInterface` as needed to assemble results.
    """

    @abstractmethod
    def entity_history(
        self,
        entity_id: str,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> QueryResult:
        """
        Return the full event history for a given entity.

        Args:
            entity_id: ID of the entity to query.
            since:     Optional start of the time window (inclusive).
            until:     Optional end of the time window (inclusive).

        Returns:
            QueryResult whose `data` contains a list of event dicts
            ordered by timestamp ascending.
        """
        ...

    @abstractmethod
    def entities_at_time(self, timestamp: float) -> QueryResult:
        """
        Return the state of all known entities at a given timestamp.

        Args:
            timestamp: The simulation clock time to reconstruct.

        Returns:
            QueryResult whose `data` contains one dict per entity,
            each with `entity_id`, `entity_type`, and `state`.
        """
        ...

    @abstractmethod
    def events_in_range(
        self,
        since: float,
        until: float,
        event_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
    ) -> QueryResult:
        """
        Return all events within a time range, with optional filters.

        Args:
            since:            Start of the time range (inclusive).
            until:            End of the time range (inclusive).
            event_type:       Optional filter by event type string.
            source_entity_id: Optional filter by the causing entity.

        Returns:
            QueryResult whose `data` is a list of event dicts.
        """
        ...

    @abstractmethod
    def beliefs_for_entity(
        self,
        entity_id: str,
        predicate: Optional[str] = None,
    ) -> QueryResult:
        """
        Return all current beliefs about an entity.

        Args:
            entity_id: ID of the entity to query.
            predicate: Optional filter by belief predicate name.

        Returns:
            QueryResult whose `data` contains one dict per belief.
        """
        ...

    @abstractmethod
    def raw_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> QueryResult:
        """
        Execute a raw backend-specific query (e.g. Cypher for Neo4j).

        Intended for power users and debugging.  Callers must be aware
        of the underlying backend.

        Args:
            query:  The raw query string.
            params: Optional query parameters.

        Returns:
            QueryResult whose `data` contains raw result rows.
        """
        ...
