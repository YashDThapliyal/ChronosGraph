"""
Cypher-backed query adapter for MCP tools.

Provides the same method signatures as WorldQueryAPI (where_is, where_was,
what_happened) so MCP tools can call either transparently, plus two
graph-native methods that have no WorldQueryAPI equivalent.
"""

from __future__ import annotations

from typing import Any


class GraphQueryAPI:
    """Read-only query interface backed by Neo4j Cypher queries."""

    def __init__(self, graph: Any) -> None:  # graph: Neo4jGraph
        self._graph = graph

    # ------------------------------------------------------------------ #
    # WorldQueryAPI-compatible methods
    # ------------------------------------------------------------------ #

    def where_is(self, entity_id: str) -> dict[str, Any]:
        """Return the current container of an entity."""
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
        """Return the container of an entity at a given timestamp."""
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

    def what_happened(self, entity_id: str) -> list[dict[str, Any]]:
        """Return all events for an entity, ordered by timestamp."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})-[:HAD_EVENT]->(ev:Event)
            RETURN properties(ev) AS ev
            ORDER BY ev.timestamp ASC
            """,
            {"entity_id": entity_id},
        )
        return [_event_props_to_dict(row["ev"]) for row in rows]

    # ------------------------------------------------------------------ #
    # Graph-native methods (no WorldQueryAPI equivalent)
    # ------------------------------------------------------------------ #

    def whats_inside(self, container_id: str) -> list[dict[str, Any]]:
        """Return all entities currently inside a given container."""
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
        """Return all entities that were inside a container at a given timestamp."""
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

    def list_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        """Return all tracked entity IDs, optionally filtered by type."""
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
        """Return all entity IDs that have ever acted as a container."""
        rows = self._graph.run_cypher(
            """
            MATCH ()-[:INSIDE]->(c:Entity)
            RETURN DISTINCT c.entity_id AS container_id
            ORDER BY c.entity_id
            """,
            {},
        )
        return [r["container_id"] for r in rows]

    def find_co_located(self, entity_id: str, timestamp: float) -> list[dict[str, Any]]:
        """Return all other entities that were in the same container as entity_id at timestamp."""
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})-[r1:INSIDE]->(c:Entity)
            WHERE r1.from_time <= $timestamp
              AND (r1.to_time IS NULL OR r1.to_time > $timestamp)
            MATCH (other:Entity)-[r2:INSIDE]->(c)
            WHERE r2.from_time <= $timestamp
              AND (r2.to_time IS NULL OR r2.to_time > $timestamp)
              AND other.entity_id <> $entity_id
            RETURN other.entity_id AS entity_id,
                   other.entity_type AS entity_type,
                   c.entity_id AS shared_container
            ORDER BY other.entity_id
            """,
            {"entity_id": entity_id, "timestamp": timestamp},
        )
        return [
            {
                "entity_id":        r["entity_id"],
                "entity_type":      r["entity_type"],
                "shared_container": r["shared_container"],
            }
            for r in rows
        ]

    def get_containment_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Return every container an entity has been inside, in order."""
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
# Helper
# ------------------------------------------------------------------ #

def _event_props_to_dict(props: dict[str, Any]) -> dict[str, Any]:
    """Normalise an Event node's properties for MCP tool output."""
    result: dict[str, Any] = {
        "event_id":   props.get("event_id"),
        "event_type": props.get("event_type"),
        "timestamp":  props.get("timestamp"),
        "parent":     props.get("new_parent"),
        "visible":    props.get("new_visibility"),
        "position":   None,
    }
    if "new_x" in props:
        result["position"] = {
            "x": props["new_x"],
            "y": props["new_y"],
            "z": props["new_z"],
        }
    return result
