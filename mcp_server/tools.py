"""
MCP tool registry for ChronosGraph world-memory queries.

Tool design principles
----------------------
The graph stores one thing: (Entity)-[:INSIDE {from_time, to_time}]->(Entity).

Every question an agent asks about this world is either:
  - Forward traversal  : given an entity, find its container(s)
  - Reverse traversal  : given a container, find its entity/entities
  - Discovery          : enumerate what entities or containers exist

This gives exactly 8 tools — 3 forward + 3 reverse + 2 discovery.
Nothing is added unless it would otherwise require N+1 round-trips for a
common query that the database can answer in one Cypher statement.

Tools deliberately omitted
--------------------------
  get_event_history   -- raw Neo4j event nodes; overlaps with
                         get_containment_history and adds no new information
                         for location questions.
  find_co_located     -- pure 2-call composition: get_parent_at gives the
                         container, find_entities_in_container_at gives the
                         co-occupants. No dedicated tool needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from query_api.world_query_api import WorldQueryAPI

if TYPE_CHECKING:
    from query_api.graph_query_api import GraphQueryAPI


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """Static MCP tool metadata and callable."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: ToolHandler

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }


def build_tool_registry(
    api: WorldQueryAPI,
    graph_api: Optional["GraphQueryAPI"] = None,
) -> dict[str, ToolDefinition]:
    """
    Build the tool registry.

    The three core tools (get_current_parent, get_parent_at,
    get_containment_history) work with either the in-memory WorldQueryAPI or
    the Cypher-backed GraphQueryAPI.  The remaining five tools require Neo4j
    and are only registered when graph_api is provided.
    """
    _query_api = graph_api if graph_api is not None else api

    # ------------------------------------------------------------------
    # Forward traversal — entity → container
    # ------------------------------------------------------------------

    def get_current_parent(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        result = _query_api.where_is(entity_id)
        return {"entity_id": entity_id, "parent": result["parent"]}

    def get_parent_at(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        timestamp = _require_number(arguments, "timestamp")
        result = _query_api.where_was(entity_id, timestamp)
        return {"entity_id": entity_id, "timestamp": timestamp, "parent": result["parent"]}

    registry: dict[str, ToolDefinition] = {
        "get_current_parent": ToolDefinition(
            name="get_current_parent",
            description=(
                "Return the container an entity is inside right now. "
                "Use this for any question about where something currently is."
            ),
            input_schema={
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "parent":    {"type": ["string", "null"]},
                },
                "required": ["entity_id", "parent"],
                "additionalProperties": False,
            },
            handler=get_current_parent,
        ),
        "get_parent_at": ToolDefinition(
            name="get_parent_at",
            description=(
                "Return the container an entity was inside at a specific timestamp. "
                "Use this for any question about where something was at a point in time."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "timestamp": {"type": "number"},
                },
                "required": ["entity_id", "timestamp"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "timestamp": {"type": "number"},
                    "parent":    {"type": ["string", "null"]},
                },
                "required": ["entity_id", "timestamp", "parent"],
                "additionalProperties": False,
            },
            handler=get_parent_at,
        ),
    }

    # ------------------------------------------------------------------
    # Reverse traversal + discovery — require Neo4j
    # ------------------------------------------------------------------

    if graph_api is not None:

        def get_containment_history(arguments: dict[str, Any]) -> dict[str, Any]:
            entity_id = _require_string(arguments, "entity_id")
            history = graph_api.get_containment_history(entity_id)
            return {"entity_id": entity_id, "history": history}

        registry["get_containment_history"] = ToolDefinition(
            name="get_containment_history",
            description=(
                "Return every container an entity has ever been inside, in chronological order, "
                "with the timestamps when each period started and ended. "
                "Use this to trace an entity's full movement history or reason about sequences."
            ),
            input_schema={
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "history": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "container": {"type": "string"},
                                "from_time": {"type": "number"},
                                "to_time":   {"type": ["number", "null"]},
                            },
                            "required": ["container", "from_time", "to_time"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["entity_id", "history"],
                "additionalProperties": False,
            },
            handler=get_containment_history,
        )

        def find_entities_in_container(arguments: dict[str, Any]) -> dict[str, Any]:
            container_id = _require_string(arguments, "container_id")
            entities = graph_api.whats_inside(container_id)
            return {"container_id": container_id, "entities": entities}

        def find_entities_in_container_at(arguments: dict[str, Any]) -> dict[str, Any]:
            container_id = _require_string(arguments, "container_id")
            timestamp    = _require_number(arguments, "timestamp")
            entities     = graph_api.whats_inside_at(container_id, timestamp)
            return {"container_id": container_id, "timestamp": timestamp, "entities": entities}

        def find_entities_ever_in_container(arguments: dict[str, Any]) -> dict[str, Any]:
            container_id = _require_string(arguments, "container_id")
            entities     = graph_api.who_ever_was_in(container_id)
            return {"container_id": container_id, "entities": entities}

        def list_entities(arguments: dict[str, Any]) -> dict[str, Any]:
            entity_type = arguments.get("entity_type")
            if entity_type is not None and not isinstance(entity_type, str):
                raise ValueError("entity_type must be a string if provided")
            entities = graph_api.list_entities(entity_type or None)
            return {"entities": entities}

        def list_containers(arguments: dict[str, Any]) -> dict[str, Any]:
            return {"containers": graph_api.list_containers()}

        registry["find_entities_in_container"] = ToolDefinition(
            name="find_entities_in_container",
            description=(
                "Return all entities currently inside a container. "
                "Use this for any question about what is in a place right now."
            ),
            input_schema={
                "type": "object",
                "properties": {"container_id": {"type": "string"}},
                "required": ["container_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id":   {"type": "string"},
                                "entity_type": {"type": "string"},
                                "since":       {"type": "number"},
                            },
                            "required": ["entity_id", "entity_type", "since"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["container_id", "entities"],
                "additionalProperties": False,
            },
            handler=find_entities_in_container,
        )

        registry["find_entities_in_container_at"] = ToolDefinition(
            name="find_entities_in_container_at",
            description=(
                "Return all entities that were inside a container at a specific timestamp. "
                "Use this for any question about what was in a place at a point in time."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "timestamp":    {"type": "number"},
                },
                "required": ["container_id", "timestamp"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "timestamp":    {"type": "number"},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id":   {"type": "string"},
                                "entity_type": {"type": "string"},
                                "from_time":   {"type": "number"},
                                "to_time":     {"type": ["number", "null"]},
                            },
                            "required": ["entity_id", "entity_type", "from_time", "to_time"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["container_id", "timestamp", "entities"],
                "additionalProperties": False,
            },
            handler=find_entities_in_container_at,
        )

        registry["find_entities_ever_in_container"] = ToolDefinition(
            name="find_entities_ever_in_container",
            description=(
                "Return all entities that have ever been inside a container — not just current "
                "occupants. Use this for any question about what has historically been in a place."
            ),
            input_schema={
                "type": "object",
                "properties": {"container_id": {"type": "string"}},
                "required": ["container_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id":   {"type": "string"},
                                "entity_type": {"type": "string"},
                            },
                            "required": ["entity_id", "entity_type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["container_id", "entities"],
                "additionalProperties": False,
            },
            handler=find_entities_ever_in_container,
        )

        registry["list_entities"] = ToolDefinition(
            name="list_entities",
            description=(
                "Return all entity IDs tracked in the world model. "
                "Call this first when you do not know what entities exist."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Optional. Filter by entity type. Omit to list all.",
                    }
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id":   {"type": "string"},
                                "entity_type": {"type": "string"},
                            },
                            "required": ["entity_id", "entity_type"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["entities"],
                "additionalProperties": False,
            },
            handler=list_entities,
        )

        registry["list_containers"] = ToolDefinition(
            name="list_containers",
            description=(
                "Return all container IDs that have ever held at least one entity. "
                "Call this first when you do not know what containers exist."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "containers": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["containers"],
                "additionalProperties": False,
            },
            handler=list_containers,
        )

    return registry


def _require_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string for '{key}'")
    return value


def _require_number(arguments: dict[str, Any], key: str) -> float:
    value = arguments.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"Expected number for '{key}'")
    return float(value)
