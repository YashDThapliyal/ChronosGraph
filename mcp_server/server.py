"""Spec-compliant JSON-RPC 2.0 MCP server over stdio."""

from __future__ import annotations

import json
import sys
from typing import Any

from chronosgraph.bootstrap import bootstrap_world
from query_api.world_query_api import WorldQueryAPI
from world.world_state_engine import WorldStateEngine

from .tools import ToolDefinition, build_tool_registry

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MethodNotFoundError(Exception):
    """Raised when a JSON-RPC method is not implemented."""


class MCPServer:
    """Minimal MCP server implementing tools/list and tools/call."""

    def __init__(
        self,
        query_api: WorldQueryAPI,
        graph_api: Any = None,
    ) -> None:
        self._tool_registry = build_tool_registry(query_api, graph_api=graph_api)

    def serve_stdio(self) -> None:
        """Read JSON-RPC requests from stdin and write responses to stdout."""
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            response_payload = self._handle_json_line(line)
            if response_payload is None:
                continue
            self._write_json(response_payload)

    def _handle_json_line(self, line: str) -> dict[str, Any] | list[dict[str, Any]] | None:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return self._error_response(None, PARSE_ERROR, "Parse error")

        if isinstance(parsed, list):
            if not parsed:
                return self._error_response(None, INVALID_REQUEST, "Invalid Request")
            responses: list[dict[str, Any]] = []
            for item in parsed:
                response = self._handle_request(item)
                if response is not None:
                    responses.append(response)
            return responses or None

        return self._handle_request(parsed)

    def _handle_request(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return self._error_response(None, INVALID_REQUEST, "Invalid Request")

        request_id = request.get("id")
        is_notification = "id" not in request

        if request.get("jsonrpc") != "2.0" or "method" not in request:
            if is_notification:
                return None
            return self._error_response(request_id, INVALID_REQUEST, "Invalid Request")

        method = request["method"]
        params = request.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if is_notification:
                return None
            return self._error_response(request_id, INVALID_PARAMS, "Invalid params")

        try:
            result = self._dispatch(method, params)
        except MethodNotFoundError:
            if is_notification:
                return None
            return self._error_response(request_id, METHOD_NOT_FOUND, "Method not found")
        except ValueError as exc:
            if is_notification:
                return None
            return self._error_response(request_id, INVALID_PARAMS, str(exc))
        except Exception:
            if is_notification:
                return None
            return self._error_response(request_id, INTERNAL_ERROR, "Internal error")

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "tools/list":
            return self._handle_tools_list()
        if method == "tools/call":
            return self._handle_tools_call(params)
        raise MethodNotFoundError(method)

    def _handle_tools_list(self) -> dict[str, Any]:
        tools = [
            tool.metadata()
            for tool in self._tool_registry.values()
        ]
        return {"tools": tools}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str):
            raise ValueError("Expected string 'name' in tools/call params")
        if not isinstance(arguments, dict):
            raise ValueError("Expected object 'arguments' in tools/call params")

        tool: ToolDefinition | None = self._tool_registry.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        output = tool.handler(arguments)
        return {"name": tool.name, "output": output}

    @staticmethod
    def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    @staticmethod
    def _write_json(payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def main() -> None:
    """Run stdio MCP server."""
    from config.settings import ChronosGraphSettings
    settings = ChronosGraphSettings()

    neo4j_graph = None
    graph_api = None

    if settings.use_neo4j:
        from graph.neo4j_graph import Neo4jGraph
        from query_api.graph_query_api import GraphQueryAPI
        neo4j_graph = Neo4jGraph(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        neo4j_graph.connect()
        graph_api = GraphQueryAPI(neo4j_graph)

    try:
        result = bootstrap_world(demo=False, neo4j_graph=neo4j_graph)
        world_engine = result if isinstance(result, WorldStateEngine) else result[0]
        query_api = WorldQueryAPI(world_engine)
        server = MCPServer(query_api, graph_api=graph_api)
        server.serve_stdio()
    finally:
        if neo4j_graph is not None:
            neo4j_graph.disconnect()


if __name__ == "__main__":
    main()
