"""MCP tool registry for ChronosGraph world-memory queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from query_api.world_query_api import WorldQueryAPI


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


def build_tool_registry(api: WorldQueryAPI) -> dict[str, ToolDefinition]:
    """Create the MCP tool map for the current API instance."""

    def get_current_parent(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        result = api.where_is(entity_id)
        return {"parent": result["parent"]}

    def get_parent_at(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        timestamp = _require_number(arguments, "timestamp")
        result = api.where_was(entity_id, timestamp)
        return {"parent": result["parent"]}

    def get_event_history(arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _require_string(arguments, "entity_id")
        history = api.what_happened(entity_id)
        return {"history": history}

    return {
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
                "properties": {
                    "parent": {"type": ["string", "null"]},
                },
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
                "properties": {
                    "parent": {"type": ["string", "null"]},
                },
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
                                "timestamp": {"type": "number"},
                                "parent": {"type": ["string", "null"]},
                                "position": {
                                    "type": ["object", "null"],
                                    "properties": {
                                        "x": {"type": "number"},
                                        "y": {"type": "number"},
                                        "z": {"type": "number"},
                                    },
                                    "required": ["x", "y", "z"],
                                    "additionalProperties": False,
                                },
                                "visible": {"type": "boolean"},
                            },
                            "required": ["timestamp", "parent", "position", "visible"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["history"],
                "additionalProperties": False,
            },
            handler=get_event_history,
        ),
    }


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
