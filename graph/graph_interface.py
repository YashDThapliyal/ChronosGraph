"""
Abstract interface for graph database operations.

ChronosGraph stores its temporal knowledge as a property graph where
entities are nodes, relationships are typed edges, and all data carries
timestamp attributes.  This interface hides the concrete backend
(Neo4j, NetworkX, etc.) from the rest of the system.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class GraphInterface(ABC):
    """
    Defines the contract for graph database interactions.

    All graph writes and reads must go through this interface so that
    the backend can be swapped without touching `core/`, `storage/`, or
    `queries/`.
    """

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    @abstractmethod
    def connect(self) -> None:
        """
        Establish a connection to the graph backend.

        Should be idempotent — calling connect on an already-connected
        instance must not raise.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and release resources."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Return True if the backend connection is currently active.

        Returns:
            Connection status.
        """
        ...

    # ------------------------------------------------------------------ #
    # Node operations
    # ------------------------------------------------------------------ #

    @abstractmethod
    def create_node(
        self,
        label: str,
        properties: dict[str, Any],
        node_id: Optional[str] = None,
    ) -> str:
        """
        Create a new node in the graph.

        Args:
            label:      Node label / type (e.g. "Entity", "Event").
            properties: Key-value properties to attach to the node.
            node_id:    Optional explicit ID.  Auto-generated if None.

        Returns:
            The ID of the newly created node.
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a node by its ID.

        Args:
            node_id: ID of the node to retrieve.

        Returns:
            Node properties dict including its label, or None if absent.
        """
        ...

    @abstractmethod
    def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        """
        Merge new properties into an existing node.

        Args:
            node_id:    ID of the node to update.
            properties: Properties to set or overwrite.
        """
        ...

    @abstractmethod
    def delete_node(self, node_id: str) -> None:
        """
        Delete a node and all of its relationships.

        Args:
            node_id: ID of the node to delete.
        """
        ...

    # ------------------------------------------------------------------ #
    # Relationship operations
    # ------------------------------------------------------------------ #

    @abstractmethod
    def create_relationship(
        self,
        from_node_id: str,
        to_node_id: str,
        rel_type: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Create a directed relationship between two nodes.

        Args:
            from_node_id: ID of the source node.
            to_node_id:   ID of the target node.
            rel_type:     Relationship type string (e.g. "MOVED_TO",
                          "CAUSED", "NEAR").
            properties:   Optional key-value properties on the edge.

        Returns:
            The ID of the newly created relationship.
        """
        ...

    @abstractmethod
    def get_relationships(
        self,
        node_id: str,
        rel_type: Optional[str] = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """
        Retrieve relationships connected to a node.

        Args:
            node_id:   ID of the node to query.
            rel_type:  Optional filter by relationship type.
            direction: One of "out", "in", or "both".

        Returns:
            List of relationship dicts, each containing `id`, `type`,
            `from_node_id`, `to_node_id`, and `properties`.
        """
        ...

    # ------------------------------------------------------------------ #
    # Traversal
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_neighbors(
        self,
        node_id: str,
        rel_type: Optional[str] = None,
        direction: str = "out",
    ) -> list[dict[str, Any]]:
        """
        Return neighbouring nodes, optionally filtered by relationship type.

        Args:
            node_id:   Starting node ID.
            rel_type:  Optional relationship type to follow.
            direction: Edge direction to traverse ("out", "in", "both").

        Returns:
            List of neighbour node property dicts.
        """
        ...
