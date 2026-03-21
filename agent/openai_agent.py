"""OpenAI tool-calling agent over ChronosGraph MCP-style tool registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mcp_server.tools import ToolDefinition

SYSTEM_PROMPT = (
    "You are an agent operating over a structured temporal world model.\n\n"
    "When calling tools, you MUST use exact entity_id values from this list.\n"
    "Do not invent entity IDs.\n"
    "Do not shorten entity names."
)


@dataclass
class ToolTrace:
    """Single tool invocation trace."""

    tool_call: dict[str, Any]
    tool_result: dict[str, Any]


@dataclass
class AgentResponse:
    """Final response payload for CLI display."""

    answer: str
    traces: list[ToolTrace]


class OpenAIToolAgent:
    """OpenAI-backed agent that executes tool calls from a registry."""

    def __init__(
        self,
        registry: dict[str, ToolDefinition],
        model: str = "gpt-4.1",
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency error path
            raise RuntimeError(
                "OpenAI SDK is not installed. Install with: pip install openai"
            ) from exc

        self._client = OpenAI()
        self._registry = registry
        self._model = model
        self._system_prompt = system_prompt
        self._tools = self._convert_tools(registry)

    @staticmethod
    def _convert_tools(registry: dict[str, ToolDefinition]) -> list[dict[str, Any]]:
        """Convert MCP tool definitions into OpenAI tools schema."""
        converted: list[dict[str, Any]] = []
        for tool in registry.values():
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
            )
        return converted

    def run_without_tools(self, user_question: str) -> AgentResponse:
        """Single chat completion with no tools; model answers from reasoning only."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_question},
        ]
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        answer = completion.choices[0].message.content or ""
        return AgentResponse(answer=answer, traces=[])

    def run_with_tools(self, user_question: str, max_round_trips: int = 8) -> AgentResponse:
        """Run tool-calling loop and return final answer + tool traces."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_question},
        ]
        traces: list[ToolTrace] = []

        for _ in range(max_round_trips):
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tools,
            )

            message = completion.choices[0].message
            tool_calls = message.tool_calls or []

            if not tool_calls:
                return AgentResponse(answer=message.content or "", traces=traces)

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = self._parse_arguments(tool_call.function.arguments)
                tool_result = self._execute_tool(tool_name, arguments)

                traces.append(
                    ToolTrace(
                        tool_call={
                            "id": tool_call.id,
                            "name": tool_name,
                            "arguments": arguments,
                        },
                        tool_result=tool_result,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result),
                    }
                )

        raise RuntimeError("Exceeded maximum tool-calling rounds without final answer")

    def ask(self, user_question: str, max_round_trips: int = 8) -> AgentResponse:
        """Convenience alias for run_with_tools."""
        return self.run_with_tools(user_question, max_round_trips)

    @staticmethod
    def _parse_arguments(raw_arguments: str) -> dict[str, Any]:
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Tool arguments are not valid JSON: {raw_arguments}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must decode to a JSON object")
        return parsed

    def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Unknown tool requested by model: {tool_name}")
        return tool.handler(arguments)
