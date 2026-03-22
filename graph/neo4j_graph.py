"""
Neo4j implementation of GraphInterface.

Uses the official neo4j Python driver (>=5.0).  All dynamic values are
passed as Cypher parameters -- never interpolated into query strings.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from graph.graph_interface import GraphInterface


class Neo4jGraph(GraphInterface):
    """Concrete graph backend backed by a Neo4j database."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Any = None  # neo4j.Driver, imported lazily

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        if self._driver is not None:
            return
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        self._driver.verify_connectivity()
        self._create_indexes()

    def disconnect(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def is_connected(self) -> bool:
        return self._driver is not None

    # ------------------------------------------------------------------ #
    # Core Cypher primitive (used by all store implementations)
    # ------------------------------------------------------------------ #

    def run_cypher(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as a list of dicts."""
        self._require_connected()
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    # ------------------------------------------------------------------ #
    # Node operations
    # ------------------------------------------------------------------ #

    def create_node(
        self,
        label: str,
        properties: dict[str, Any],
        node_id: Optional[str] = None,
    ) -> str:
        self._require_connected()
        nid = node_id or str(uuid4())
        props = {**properties, "node_id": nid}
        # Label cannot be parameterised in Cypher — sanitise to alphanum only
        safe_label = _safe_label(label)
        self.run_cypher(
            f"CREATE (n:{safe_label}) SET n = $props",
            {"props": props},
        )
        return nid

    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        rows = self.run_cypher(
            "MATCH (n {node_id: $node_id}) RETURN properties(n) AS props, labels(n) AS labels LIMIT 1",
            {"node_id": node_id},
        )
        if not rows:
            return None
        result = dict(rows[0]["props"])
        result["_labels"] = rows[0]["labels"]
        return result

    def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        self.run_cypher(
            "MATCH (n {node_id: $node_id}) SET n += $props",
            {"node_id": node_id, "props": properties},
        )

    def delete_node(self, node_id: str) -> None:
        self.run_cypher(
            "MATCH (n {node_id: $node_id}) DETACH DELETE n",
            {"node_id": node_id},
        )

    # ------------------------------------------------------------------ #
    # Relationship operations
    # ------------------------------------------------------------------ #

    def create_relationship(
        self,
        from_node_id: str,
        to_node_id: str,
        rel_type: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> str:
        rid = str(uuid4())
        props = {**(properties or {}), "rel_id": rid}
        safe_rel = _safe_label(rel_type)
        self.run_cypher(
            f"MATCH (a {{node_id: $from_id}}), (b {{node_id: $to_id}}) "
            f"CREATE (a)-[r:{safe_rel}]->(b) SET r = $props",
            {"from_id": from_node_id, "to_id": to_node_id, "props": props},
        )
        return rid

    def get_relationships(
        self,
        node_id: str,
        rel_type: Optional[str] = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        self._require_connected()
        safe_rel = f":{_safe_label(rel_type)}" if rel_type else ""
        if direction == "out":
            pattern = f"(n {{node_id: $node_id}})-[r{safe_rel}]->(m)"
        elif direction == "in":
            pattern = f"(n {{node_id: $node_id}})<-[r{safe_rel}]-(m)"
        else:
            pattern = f"(n {{node_id: $node_id}})-[r{safe_rel}]-(m)"
        rows = self.run_cypher(
            f"MATCH {pattern} RETURN r, m.node_id AS other_id",
            {"node_id": node_id},
        )
        results = []
        for row in rows:
            r = row["r"]
            results.append({
                "id": r.get("rel_id", ""),
                "type": type(r).__name__,
                "from_node_id": node_id,
                "to_node_id": row["other_id"],
                "properties": dict(r),
            })
        return results

    # ------------------------------------------------------------------ #
    # Traversal
    # ------------------------------------------------------------------ #

    def get_neighbors(
        self,
        node_id: str,
        rel_type: Optional[str] = None,
        direction: str = "out",
    ) -> list[dict[str, Any]]:
        safe_rel = f":{_safe_label(rel_type)}" if rel_type else ""
        if direction == "out":
            pattern = f"(n {{node_id: $node_id}})-[r{safe_rel}]->(m)"
        elif direction == "in":
            pattern = f"(n {{node_id: $node_id}})<-[r{safe_rel}]-(m)"
        else:
            pattern = f"(n {{node_id: $node_id}})-[r{safe_rel}]-(m)"
        rows = self.run_cypher(
            f"MATCH {pattern} RETURN properties(m) AS props, labels(m) AS labels",
            {"node_id": node_id},
        )
        results = []
        for row in rows:
            neighbour = dict(row["props"])
            neighbour["_labels"] = row["labels"]
            results.append(neighbour)
        return results

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _require_connected(self) -> None:
        if self._driver is None:
            raise RuntimeError("Neo4jGraph is not connected. Call connect() first.")

    def _create_indexes(self) -> None:
        statements = [
            "CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) ON (e.entity_id)",
            "CREATE INDEX event_id_index IF NOT EXISTS FOR (ev:Event) ON (ev.event_id)",
            "CREATE INDEX event_type_index IF NOT EXISTS FOR (ev:Event) ON (ev.event_type)",
            "CREATE INDEX event_timestamp_index IF NOT EXISTS FOR (ev:Event) ON (ev.timestamp)",
        ]
        with self._driver.session() as session:
            for stmt in statements:
                session.run(stmt)


def _safe_label(label: str) -> str:
    """Return only alphanumeric + underscore characters to prevent Cypher injection via labels."""
    return "".join(c for c in label if c.isalnum() or c == "_")
