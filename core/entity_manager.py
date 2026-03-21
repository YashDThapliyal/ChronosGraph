"""
Abstract interface for managing entity lifecycle and current state.

The EntityManager is the authoritative source for *current* entity state
within the core system.  It does not deal with history — that is the
responsibility of the storage layer.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class EntityManagerInterface(ABC):
    """
    Manages the in-flight state of tracked entities.

    An entity is any uniquely identifiable thing observed by the
    simulator: an agent, an object, a zone, etc.
    """

    @abstractmethod
    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        attributes: dict[str, Any],
        timestamp: float = 0.0,
    ) -> None:
        """
        Create or update an entity with new state.

        If the entity does not exist it is created.  If it exists its
        attributes are merged with the provided values (existing keys
        not present in `attributes` are retained).

        Args:
            entity_id:   Unique identifier of the entity.
            entity_type: Category label (e.g. "agent", "object").
            attributes:  Key-value state to apply.
            timestamp:   Simulation time of this update.
        """
        ...

    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve the current state of an entity.

        Args:
            entity_id: ID of the entity to retrieve.

        Returns:
            A dict of entity state, or None if the entity is unknown.
        """
        ...

    @abstractmethod
    def remove_entity(self, entity_id: str) -> None:
        """
        Remove an entity from active tracking.

        Does not delete historical records from storage.

        Args:
            entity_id: ID of the entity to remove.
        """
        ...

    @abstractmethod
    def list_entities(self) -> list[str]:
        """
        Return IDs of all currently tracked entities.

        Returns:
            A list of entity ID strings.
        """
        ...
