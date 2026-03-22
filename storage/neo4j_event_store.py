"""
Neo4j implementation of EventStoreInterface.

Each event is stored as a :Event node with type-specific properties.
A (Entity)-[:HAD_EVENT]->(Event) relationship links it to its subject.
"""

from __future__ import annotations

from typing import Any, Optional

from core.event_engine import (
    Event,
    MovedEvent,
    RelationshipChangedEvent,
    VisibilityChangedEvent,
)
from storage.event_store import EventStoreInterface


class Neo4jEventStore(EventStoreInterface):
    """Persists events as nodes in Neo4j."""

    def __init__(self, graph: Any) -> None:  # graph: Neo4jGraph
        self._graph = graph

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    def save_event(self, event: Event) -> None:
        params = _event_to_params(event)
        self._graph.run_cypher(
            """
            MERGE (e:Entity {entity_id: $entity_id})
            ON CREATE SET e.entity_type = $entity_type
            CREATE (ev:Event {
                event_id:          $event_id,
                event_type:        $event_type,
                timestamp:         $timestamp,
                subject_entity_id: $entity_id
            })
            SET ev += $extra_props
            CREATE (e)-[:HAD_EVENT]->(ev)
            """,
            params,
        )

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        rows = self._graph.run_cypher(
            "MATCH (ev:Event {event_id: $event_id}) RETURN properties(ev) AS props",
            {"event_id": event_id},
        )
        if not rows:
            return None
        return _node_to_event(rows[0]["props"])

    def get_events(
        self,
        event_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[Event]:
        query = "MATCH (ev:Event) WHERE 1=1"
        params: dict[str, Any] = {}

        if event_type is not None:
            query += " AND ev.event_type = $event_type"
            params["event_type"] = event_type
        if source_entity_id is not None:
            query += " AND ev.subject_entity_id = $source_entity_id"
            params["source_entity_id"] = source_entity_id
        if since is not None:
            query += " AND ev.timestamp >= $since"
            params["since"] = since
        if until is not None:
            query += " AND ev.timestamp <= $until"
            params["until"] = until

        query += " RETURN properties(ev) AS props ORDER BY ev.timestamp ASC"

        if limit is not None:
            query += " LIMIT $limit"
            params["limit"] = int(limit)

        rows = self._graph.run_cypher(query, params)
        return [_node_to_event(row["props"]) for row in rows]

    def count_events(
        self,
        event_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
    ) -> int:
        query = "MATCH (ev:Event) WHERE 1=1"
        params: dict[str, Any] = {}

        if event_type is not None:
            query += " AND ev.event_type = $event_type"
            params["event_type"] = event_type
        if source_entity_id is not None:
            query += " AND ev.subject_entity_id = $source_entity_id"
            params["source_entity_id"] = source_entity_id

        query += " RETURN count(ev) AS n"
        rows = self._graph.run_cypher(query, params)
        return int(rows[0]["n"]) if rows else 0


# ------------------------------------------------------------------ #
# Serialisation helpers
# ------------------------------------------------------------------ #

def _event_to_params(event: Event) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id":    event.event_id,
        "event_type":  type(event).__name__,
        "timestamp":   event.timestamp,
        "entity_id":   event.subject_entity_id,
        "entity_type": "unknown",
        "extra_props": {},
    }
    if isinstance(event, MovedEvent):
        base["extra_props"] = {
            "old_x":    event.old_position.x,
            "old_y":    event.old_position.y,
            "old_z":    event.old_position.z,
            "new_x":    event.new_position.x,
            "new_y":    event.new_position.y,
            "new_z":    event.new_position.z,
            "distance": event.distance,
        }
    elif isinstance(event, VisibilityChangedEvent):
        base["extra_props"] = {
            "old_visibility": event.old_visibility,
            "new_visibility": event.new_visibility,
        }
    elif isinstance(event, RelationshipChangedEvent):
        base["extra_props"] = {
            "old_parent": event.old_parent,
            "new_parent": event.new_parent,
        }
    return base


def _node_to_event(props: dict[str, Any]) -> Event:
    event_type = props.get("event_type", "")
    common = {
        "event_id":          props["event_id"],
        "timestamp":         props["timestamp"],
        "subject_entity_id": props["subject_entity_id"],
    }
    if event_type == "MovedEvent":
        from simulator.models import Position
        return MovedEvent(
            **common,
            old_position=Position(props["old_x"], props["old_y"], props["old_z"]),
            new_position=Position(props["new_x"], props["new_y"], props["new_z"]),
            distance=props.get("distance", 0.0),
        )
    if event_type == "VisibilityChangedEvent":
        return VisibilityChangedEvent(
            **common,
            old_visibility=props.get("old_visibility", False),
            new_visibility=props.get("new_visibility", False),
        )
    if event_type == "RelationshipChangedEvent":
        return RelationshipChangedEvent(
            **common,
            old_parent=props.get("old_parent"),
            new_parent=props.get("new_parent"),
        )
    return Event(**common)
