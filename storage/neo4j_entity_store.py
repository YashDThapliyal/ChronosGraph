"""
Neo4j implementation of EntityStoreInterface.

Manages :Entity nodes and the temporal (Entity)-[:INSIDE]->(Entity)
relationship lifecycle.  The INSIDE relationship carries from_time and
to_time properties; to_time=null means the entity is currently inside
that container.
"""

from __future__ import annotations

from typing import Any, Optional

from storage.entity_store import EntityStoreInterface


class Neo4jEntityStore(EntityStoreInterface):
    """Persists entity state and containment history in Neo4j."""

    def __init__(self, graph: Any) -> None:  # graph: Neo4jGraph
        self._graph = graph

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    def save_snapshot(
        self,
        entity_id: str,
        entity_type: str,
        state: dict[str, Any],
        timestamp: float,
    ) -> None:
        new_parent: Optional[str] = state.get("parent")
        position = state.get("position") or {}
        params = {
            "entity_id":   entity_id,
            "entity_type": entity_type,
            "timestamp":   timestamp,
            "new_parent":  new_parent,
            "visible":     state.get("visible", False),
            "pos_x":       position.get("x"),
            "pos_y":       position.get("y"),
            "pos_z":       position.get("z"),
        }
        with self._graph._driver.session() as session:
            session.execute_write(_write_snapshot_tx, params)

    def delete_entity(self, entity_id: str) -> None:
        self._graph.run_cypher(
            "MATCH (e:Entity {entity_id: $entity_id}) DETACH DELETE e",
            {"entity_id": entity_id},
        )

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def get_latest_snapshot(self, entity_id: str) -> Optional[dict[str, Any]]:
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r:INSIDE]->(p:Entity)
            WHERE r.to_time IS NULL
            RETURN e, p.entity_id AS current_parent
            """,
            {"entity_id": entity_id},
        )
        if not rows:
            return None
        return _row_to_snapshot(rows[0])

    def get_snapshot_at(
        self, entity_id: str, timestamp: float
    ) -> Optional[dict[str, Any]]:
        rows = self._graph.run_cypher(
            """
            MATCH (e:Entity {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r:INSIDE]->(p:Entity)
            WHERE r.from_time <= $timestamp
              AND (r.to_time IS NULL OR r.to_time > $timestamp)
            RETURN e, p.entity_id AS current_parent
            ORDER BY r.from_time DESC
            LIMIT 1
            """,
            {"entity_id": entity_id, "timestamp": timestamp},
        )
        if not rows:
            return None
        return _row_to_snapshot(rows[0])

    def list_entity_ids(self) -> list[str]:
        rows = self._graph.run_cypher(
            "MATCH (e:Entity) RETURN e.entity_id AS entity_id ORDER BY e.entity_id"
        )
        return [row["entity_id"] for row in rows]


# ------------------------------------------------------------------ #
# Transaction function (runs inside execute_write)
# ------------------------------------------------------------------ #

def _write_snapshot_tx(tx: Any, params: dict[str, Any]) -> None:
    entity_id  = params["entity_id"]
    entity_type = params["entity_type"]
    timestamp  = params["timestamp"]
    new_parent = params["new_parent"]
    visible    = params["visible"]
    pos_x      = params["pos_x"]
    pos_y      = params["pos_y"]
    pos_z      = params["pos_z"]

    # Step 1 — upsert entity node
    tx.run(
        """
        MERGE (e:Entity {entity_id: $entity_id})
        ON CREATE SET e.entity_type = $entity_type
        SET e.visible   = $visible,
            e.last_seen = $timestamp,
            e.pos_x     = $pos_x,
            e.pos_y     = $pos_y,
            e.pos_z     = $pos_z
        """,
        entity_id=entity_id,
        entity_type=entity_type,
        timestamp=timestamp,
        visible=visible,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
    )

    # Step 2 — close open INSIDE if parent changed (or parent is now null)
    tx.run(
        """
        MATCH (e:Entity {entity_id: $entity_id})-[r:INSIDE]->(old_p:Entity)
        WHERE r.to_time IS NULL
          AND ($new_parent IS NULL OR old_p.entity_id <> $new_parent)
        SET r.to_time = $timestamp
        """,
        entity_id=entity_id,
        new_parent=new_parent,
        timestamp=timestamp,
    )

    # Step 3 — open new INSIDE if there is a parent and none already open
    if new_parent is not None:
        tx.run(
            """
            MATCH (e:Entity {entity_id: $entity_id})
            MERGE (p:Entity {entity_id: $new_parent})
            ON CREATE SET p.entity_type = 'unknown'
            WITH e, p
            WHERE NOT EXISTS {
                MATCH (e)-[r:INSIDE]->(p) WHERE r.to_time IS NULL
            }
            CREATE (e)-[:INSIDE {from_time: $timestamp, to_time: null}]->(p)
            """,
            entity_id=entity_id,
            new_parent=new_parent,
            timestamp=timestamp,
        )


# ------------------------------------------------------------------ #
# Result helpers
# ------------------------------------------------------------------ #

def _row_to_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    e = row["e"]
    snapshot: dict[str, Any] = {
        "entity_id":      e.get("entity_id"),
        "entity_type":    e.get("entity_type"),
        "visible":        e.get("visible", False),
        "last_seen":      e.get("last_seen"),
        "parent":         row.get("current_parent"),
    }
    pos_x = e.get("pos_x")
    pos_y = e.get("pos_y")
    pos_z = e.get("pos_z")
    if pos_x is not None and pos_y is not None and pos_z is not None:
        snapshot["position"] = {"x": pos_x, "y": pos_y, "z": pos_z}
    else:
        snapshot["position"] = None
    return snapshot
