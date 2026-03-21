"""CLI runner for ChronosGraph OpenAI tool-calling agent.

Run from project root with:
    python -m agent.agent_runner
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    os.execv(
        sys.executable,
        [sys.executable, "-m", "agent.agent_runner", *sys.argv[1:]],
    )

from chronosgraph.bootstrap import bootstrap_world
from query_api.world_query_api import WorldQueryAPI
from mcp_server.tools import build_tool_registry
from agent.openai_agent import OpenAIToolAgent

MODE_BASELINE = "baseline"
MODE_KNOWLEDGE_GRAPH = "knowledge_graph"

# Optional ANSI styling (no-op if terminal doesn't support)
C = "\033[36m"   # cyan
M = "\033[33m"   # yellow (mode)
B = "\033[1m"    # bold
R = "\033[0m"    # reset
D = "\033[2m"    # dim


def _line(char: str = "─", width: int = 52) -> str:
    return char * width


def _header(title: str) -> None:
    print()
    print(f"  {C}{B}{title}{R}")
    print(f"  {C}{_line()}{R}")


def _print_banner() -> None:
    print()
    print(f"  {C}╭{_line('─', 50)}╮{R}")
    print(f"  {C}│{R}  {B}ChronosGraph{R}  ·  temporal world model agent  {C}│{R}")
    print(f"  {C}╰{_line('─', 50)}╯{R}")
    print()


def _print_help(mode: str) -> None:
    mode_label = "Baseline" if mode == MODE_BASELINE else "Knowledge Graph"
    print(f"  {D}Commands:  ask anything  ·  {B}switch{R}{D}  change mode  ·  {B}exit{R}{D}  quit{R}")
    print(f"  {D}Mode: {M}{mode_label}{R}")
    print()


def _select_mode() -> str:
    """Prompt user for Baseline vs Knowledge Graph; return mode key."""
    print()
    print(f"  {B}Select mode:{R}")
    print(f"    {C}1{R}  Baseline       (no tools, reasoning only)")
    print(f"    {C}2{R}  Knowledge Graph (tools enabled)")
    print()
    while True:
        try:
            choice = input(f"  {M}›{R} ").strip()
        except EOFError:
            choice = ""
        if choice == "1":
            return MODE_BASELINE
        if choice == "2":
            return MODE_KNOWLEDGE_GRAPH
        print(f"  {D}Enter 1 or 2.{R}")


def _mode_label(mode: str) -> str:
    return "Baseline" if mode == MODE_BASELINE else "Knowledge Graph"


def main() -> None:
    """Bootstrap world once, then run interactive CLI QA loop."""
    if "OPENAI_API_KEY" not in os.environ or not os.environ["OPENAI_API_KEY"].strip():
        raise RuntimeError("OPENAI_API_KEY is not set in environment")

    world_engine = bootstrap_world(demo=False)
    api = WorldQueryAPI(world_engine)
    registry = build_tool_registry(api)

    entity_ids = list(world_engine.entities.keys())
    system_prompt = (
        "You are an agent operating over a structured temporal world model.\n\n"
        "The following entity IDs exist in the world:\n"
        + "\n".join(entity_ids)
        + "\n\n"
        "When calling tools, you MUST use exact entity_id values from this list.\n"
        "Do not invent entity IDs.\n"
        "Do not shorten entity names."
    )
    agent = OpenAIToolAgent(
        registry=registry,
        model="gpt-4.1",
        system_prompt=system_prompt,
    )

    _print_banner()
    mode = _select_mode()
    print()
    print(f"  {D}Ready in {M}{_mode_label(mode)}{R}{D} mode.{R}")
    _print_help(mode)

    while True:
        try:
            prompt = f"  {M}[{_mode_label(mode)}]{R} › "
            question = input(prompt).strip()
        except EOFError:
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print(f"\n  {D}Bye.{R}\n")
            break
        if question.lower() == "switch":
            mode = _select_mode()
            print(f"\n  {D}Switched to {M}{_mode_label(mode)}{R}{D}.{R}")
            _print_help(mode)
            continue
        if question.lower() in {"help", "?"}:
            _print_help(mode)
            continue

        if mode == MODE_BASELINE:
            response = agent.run_without_tools(question)
            _header("Final answer")
            print(f"  {response.answer}")
            print()
        else:
            response = agent.run_with_tools(question)
            for i, trace in enumerate(response.traces, 1):
                _header(f"Tool call {i}")
                print(f"  {D}Request{R}")
                print(json.dumps(trace.tool_call, indent=2))
                print(f"\n  {D}Result{R}")
                print(json.dumps(trace.tool_result, indent=2))
                print()
            _header("Final answer")
            print(f"  {response.answer}")
            print()


if __name__ == "__main__":
    main()
