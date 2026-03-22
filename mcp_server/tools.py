"""MCP tool registry for ChronosGraph world-memory queries."""

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
    Create the MCP tool map.

    When graph_api is provided, existing tools are backed by Neo4j Cypher
    queries and two additional graph-native tools are registered.
    """
    # Prefer graph_api for the 3 core tools when available
    _query_api = graph_api if graph_api is not None else api

    def get_current_parent(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        result = _query_api.where_is(entity_id)
        return {"parent": result["parent"]}

    def get_parent_at(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        timestamp = _require_number(arguments, "timestamp")
        result = _query_api.where_was(entity_id, timestamp)
        return {"parent": result["parent"]}

    def get_event_history(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        history = _query_api.what_happened(entity_id)
        return {"history": history}

    registry: dict[str, ToolDefinition] = {
        "get_current_parent": ToolDefinition(
            name="get_current_parent",
            description="Get the current parent receptacle of an entity.",
            input_schema={
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"parent": {"type": ["string", "null"]}},
                "required": ["parent"],
                "additionalProperties": False,
            },
            handler=get_current_parent,
        ),
        "get_parent_at": ToolDefinition(
            name="get_parent_at",
            description="Get the parent receptacle of an entity at a timestamp.",
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
                "properties": {"parent": {"type": ["string", "null"]}},
                "required": ["parent"],
                "additionalProperties": False,
            },
            handler=get_parent_at,
        ),
        "get_event_history": ToolDefinition(
            name="get_event_history",
            description="Get full state snapshot history for an entity.",
            input_schema={
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "history": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp":  {"type": "number"},
                                "parent":     {"type": ["string", "null"]},
                                "position":   {"type": ["object", "null"]},
                                "visible":    {"type": ["boolean", "null"]},
                            },
                            "additionalProperties": True,
                        },
                    }
                },
                "required": ["history"],
                "additionalProperties": False,
            },
            handler=get_event_history,
        ),
    }

    # Graph-native tools — only registered when Neo4j is available
    if graph_api is not None:

        def find_entities_in_container(arguments: dict[str, Any]) -> dict[str, Any]:
            container_id = _require_string(arguments, "container_id")
            entities = graph_api.whats_inside(container_id)
            return {"container_id": container_id, "entities": entities}

        def find_entities_in_container_at(arguments: dict[str, Any]) -> dict[str, Any]:
            container_id = _require_string(arguments, "container_id")
            timestamp = _require_number(arguments, "timestamp")
            entities = graph_api.whats_inside_at(container_id, timestamp)
            return {"container_id": container_id, "timestamp": timestamp, "entities": entities}

        def get_containment_history(arguments: dict[str, Any]) -> dict[str, Any]:
            entity_id = _require_string(arguments, "entity_id")
            history = graph_api.get_containment_history(entity_id)
            return {"entity_id": entity_id, "history": history}

        registry["find_entities_in_container"] = ToolDefinition(
            name="find_entities_in_container",
            description=(
                "Find all entities currently inside a given container. "
                "Useful for answering 'what is in the drawer right now?'"
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
                "Find all entities that were inside a given container at a specific timestamp. "
                "Use this to answer historical questions like 'what was in the drawer at t=2.0?'"
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

        registry["get_containment_history"] = ToolDefinition(
            name="get_containment_history",
            description=(
                "Get the full containment history of an entity — every container "
                "it has been inside, with timestamps showing when each period started and ended."
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
                                "container":  {"type": "string"},
                                "from_time":  {"type": "number"},
                                "to_time":    {"type": ["number", "null"]},
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
