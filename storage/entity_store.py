"""
Abstract interface for persistent entity state storage.

The EntityStore archives point-in-time snapshots of entity state so that
historical queries can reconstruct what an entity looked like at any past
moment.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class EntityStoreInterface(ABC):
    """
    Defines the contract for durable entity state persistence.

    Each call to `save_snapshot` records the entity's complete state at a
    specific simulation timestamp.  Multiple snapshots per entity are
    expected; the store must support temporal retrieval.
    """

    @abstractmethod
    def save_snapshot(
        self,
        entity_id: str,
        entity_type: str,
        state: dict[str, Any],
        timestamp: float,
    ) -> None:
        """
        Persist an entity state snapshot at a given timestamp.

        Args:
            entity_id:   Unique ID of the entity.
            entity_type: Category label of the entity.
            state:       Full attribute dictionary at this moment.
            timestamp:   Simulation clock time of this snapshot.
        """
        ...

    @abstractmethod
    def get_latest_snapshot(self, entity_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve the most recent snapshot for an entity.

        Args:
            entity_id: ID of the entity.

        Returns:
            The most recent state dict, or None if unknown.
        """
        ...

    @abstractmethod
    def get_snapshot_at(
        self, entity_id: str, timestamp: float
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve the entity state as it was at or before `timestamp`.

        Args:
            entity_id: ID of the entity.
            timestamp: The point in time to query.

        Returns:
            The closest snapshot at or before `timestamp`, or None.
        """
        ...

    @abstractmethod
    def delete_entity(self, entity_id: str) -> None:
        """
        Delete all snapshots for an entity.

        Args:
            entity_id: ID of the entity to purge.
        """
        ...

    @abstractmethod
    def list_entity_ids(self) -> list[str]:
        """
        Return IDs of all entities that have at least one snapshot.

        Returns:
            A list of entity ID strings.
        """
        ...
