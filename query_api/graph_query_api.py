"""
Cypher-backed query adapter.

Method naming mirrors the tool registry in mcp_server/tools.py.
Each method is a direct mapping to one Cypher pattern — no business logic.

Forward traversal (entity -> container):
    where_is(entity_id)                  current container
    where_was(entity_id, timestamp)      container at time T
    get_containment_history(entity_id)   full ordered chain

Reverse traversal (container -> entity):
    whats_inside(container_id)           current occupants
    whats_inside_at(container_id, t)     occupants at time T
    who_ever_was_in(container_id)        all-time members

Discovery:
    list_entities(entity_type)           enumerate tracked entities
    list_containers()                    enumerate known containers
"""

from __future__ import annotations

from typing import Any


class GraphQueryAPI:
    """Read-only query interface backed by Neo4j Cypher queries."""

    def __init__(self, graph: Any) -> None:  # graph: Neo4jGraph
        self._graph = graph

    # ------------------------------------------------------------------ #
    # Forward traversal — entity -> container
    # ------------------------------------------------------------------ #

    def where_is(self, entity_id: str) -> dict[str, Any]:
        """Current container of an entity (to_time IS NULL)."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r:INSIDE]->(c:Entity)
            WHERE r.to_time IS NULL
            RETURN c.entity_id AS parent
            """,
            {"entity_id": entity_id},
        )
        parent = rows[0]["parent"] if rows else None
        return {"entity_id": entity_id, "parent": parent}

    def where_was(self, entity_id: str, timestamp: float) -> dict[str, Any]:
        """Container of an entity at a given timestamp."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r:INSIDE]->(c:Entity)
            WHERE r.from_time <= $timestamp
              AND (r.to_time IS NULL OR r.to_time > $timestamp)
            RETURN c.entity_id AS parent
            ORDER BY r.from_time DESC
            LIMIT 1
            """,
            {"entity_id": entity_id, "timestamp": timestamp},
        )
        parent = rows[0]["parent"] if rows else None
        return {"entity_id": entity_id, "timestamp": timestamp, "parent": parent}

    def get_containment_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Every container an entity has been inside, ordered by from_time."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})-[r:INSIDE]->(c:Entity)
            RETURN c.entity_id AS container,
                   r.from_time AS from_time,
                   r.to_time   AS to_time
            ORDER BY r.from_time ASC
            """,
            {"entity_id": entity_id},
        )
        return [
            {
                "container": row["container"],
                "from_time": row["from_time"],
                "to_time":   row["to_time"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Reverse traversal — container -> entity
    # ------------------------------------------------------------------ #

    def whats_inside(self, container_id: str) -> list[dict[str, Any]]:
        """All entities currently inside a container."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity)-[r:INSIDE]->(c:Entity {entity_id: $container_id})
            WHERE r.to_time IS NULL
            RETURN e.entity_id AS entity_id,
                   e.entity_type AS entity_type,
                   r.from_time AS since
            ORDER BY e.entity_id
            """,
            {"container_id": container_id},
        )
        return [
            {
                "entity_id":   row["entity_id"],
                "entity_type": row["entity_type"],
                "since":       row["since"],
            }
            for row in rows
        ]

    def whats_inside_at(self, container_id: str, timestamp: float) -> list[dict[str, Any]]:
        """All entities that were inside a container at a given timestamp."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity)-[r:INSIDE]->(c:Entity {entity_id: $container_id})
            WHERE r.from_time <= $timestamp
              AND (r.to_time IS NULL OR r.to_time > $timestamp)
            RETURN e.entity_id AS entity_id,
                   e.entity_type AS entity_type,
                   r.from_time AS from_time,
                   r.to_time   AS to_time
            ORDER BY e.entity_id
            """,
            {"container_id": container_id, "timestamp": timestamp},
        )
        return [
            {
                "entity_id":   row["entity_id"],
                "entity_type": row["entity_type"],
                "from_time":   row["from_time"],
                "to_time":     row["to_time"],
            }
            for row in rows
        ]

    def who_ever_was_in(self, container_id: str) -> list[dict[str, Any]]:
        """All entities that have ever had an INSIDE relationship to this container."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity)-[:INSIDE]->(c:Entity {entity_id: $container_id})
            RETURN DISTINCT e.entity_id AS entity_id,
                            e.entity_type AS entity_type
            ORDER BY e.entity_id
            """,
            {"container_id": container_id},
        )
        return [{"entity_id": r["entity_id"], "entity_type": r["entity_type"]} for r in rows]

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def list_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        """All tracked entity IDs, optionally filtered by type."""
        if entity_type:
            rows = self._graph.run_cypher(
                """
                MATCH (e:Entity {entity_type: $entity_type})
                RETURN e.entity_id AS entity_id, e.entity_type AS entity_type
                ORDER BY e.entity_id
                """,
                {"entity_type": entity_type},
            )
        else:
            rows = self._graph.run_cypher(
                """
                MATCH (e:Entity)
                RETURN e.entity_id AS entity_id, e.entity_type AS entity_type
                ORDER BY e.entity_id
                """,
                {},
            )
        return [{"entity_id": r["entity_id"], "entity_type": r["entity_type"]} for r in rows]

    def list_containers(self) -> list[str]:
        """All entity IDs that have ever acted as a container."""
        rows = self._graph.run_cypher(
            """
            MATCH ()-[:INSIDE]->(c:Entity)
            RETURN DISTINCT c.entity_id AS container_id
            ORDER BY c.entity_id
            """,
            {},
        )
        return [r["container_id"] for r in rows]
