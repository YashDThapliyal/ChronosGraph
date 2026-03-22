"""
ChronosGraph benchmark: three-way comparison of LLM memory strategies.

Modes
-----
  blind   -- LLM receives only the question (no world data, no tools)
  context -- LLM receives a full text dump of the world state in the prompt
  graph   -- LLM receives MCP tools backed by Neo4j and resolves answers via Cypher

For each of the 10 questions in questions.py, all three modes are run and the
answer is scored by an LLM judge against the ground truth derived from the graph.

Usage
-----
  python -m benchmark.run [--model gpt-4.1] [--judge-model gpt-4.1] [--out results.json]

Requirements
------------
  - Neo4j running at bolt://localhost:7687 (default creds: neo4j / testpassword)
    docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=neo4j/testpassword neo4j:5
  - OPENAI_API_KEY set in environment
  - pip install openai neo4j
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

from agent.openai_agent import OpenAIToolAgent
from benchmark.questions import MEGA_QUESTIONS, QUESTIONS
from chronosgraph.bootstrap import bootstrap_world
from graph.neo4j_graph import Neo4jGraph
from mcp_server.tools import build_tool_registry
from query_api.graph_query_api import GraphQueryAPI
from query_api.world_query_api import WorldQueryAPI
from world.world_state_engine import WorldStateEngine

# ---------------------------------------------------------------------------
# Shared system prompt (identical for all three modes)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_COMPLEX = (
    "You are an agent with access to a temporal world model.\n"
    "The world contains entities (objects and containers) that move between "
    "locations over time.\n\n"
    "Entity IDs used in this episode:\n"
    "  keys_001   -- a set of keys\n"
    "  card_001   -- a credit card\n"
    "  drawer_01  -- a kitchen drawer\n"
    "  counter_01 -- a kitchen counter\n"
    "  table_01   -- a table\n\n"
    "Answer concisely and precisely. "
    "When asked for a list, return items separated by commas. "
    "When asked yes/no, start your answer with 'yes' or 'no'."
)

SYSTEM_PROMPT_MEGA = (
    "You are an agent with access to a temporal world model.\n"
    "The world contains entities (objects and containers) that move between "
    "locations over time.\n\n"
    "Entity IDs used in this episode:\n"
    "  keys_001    -- a set of keys\n"
    "  card_001    -- a credit card\n"
    "  knife_001   -- a kitchen knife\n"
    "  mug_001     -- a mug\n"
    "  spatula_001 -- a spatula\n"
    "  drawer_01   -- a kitchen drawer\n"
    "  counter_01  -- a kitchen counter\n"
    "  fridge_01   -- a refrigerator\n\n"
    "Answer concisely and precisely. "
    "When asked for a list, return items separated by commas. "
    "When asked yes/no, start your answer with 'yes' or 'no'."
)

# Alias for backwards compatibility — default is complex episode
SYSTEM_PROMPT = SYSTEM_PROMPT_COMPLEX

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "testpassword"


# ---------------------------------------------------------------------------
# Context builder (for context-stuffed mode)
# ---------------------------------------------------------------------------

def build_context(graph_api: GraphQueryAPI) -> str:
    """
    Produce a complete text dump of the world state from Neo4j.

    Dynamically discovers all tracked entities and containers from the graph
    so the context is complete regardless of episode size.
    """
    lines: list[str] = ["=== WORLD STATE DUMP ===\n"]

    # Discover all tracked entities and containers from the graph
    all_entities   = [e["entity_id"] for e in graph_api.list_entities()]
    all_containers = graph_api.list_containers()
    # Moveable objects = entities that have containment history (have been inside something)
    moveable   = [e for e in all_entities if e not in all_containers]
    containers = all_containers

    # Current location of each moveable object
    lines.append("--- Current Locations ---")
    for eid in moveable:
        result = graph_api.where_is(eid)
        lines.append(f"  {eid}: {result['parent'] or 'unknown'}")

    lines.append("")

    # Full containment history
    lines.append("--- Containment History (chronological) ---")
    for eid in moveable:
        history = graph_api.get_containment_history(eid)
        if history:
            lines.append(f"  {eid}:")
            for h in history:
                to_str = f"{h['to_time']:.2f}" if h["to_time"] is not None else "NOW"
                lines.append(f"    t={h['from_time']:.2f} -> {to_str}  in {h['container']}")
        else:
            lines.append(f"  {eid}: no history recorded")

    lines.append("")

    # What is currently inside each container
    lines.append("--- Container Contents (current) ---")
    for cid in containers:
        contents = graph_api.whats_inside(cid)
        if contents:
            names = ", ".join(e["entity_id"] for e in contents)
            lines.append(f"  {cid}: {names}")
        else:
            lines.append(f"  {cid}: empty")

    lines.append("")

    # Containment timeline per entity (same data as history section, in event form)
    lines.append("--- Containment Timeline (each move event) ---")
    for eid in moveable:
        history = graph_api.get_containment_history(eid)
        if history:
            lines.append(f"  {eid}:")
            for h in history:
                to_str = f"t={h['to_time']:.2f}" if h["to_time"] is not None else "present"
                lines.append(f"    entered {h['container']} at t={h['from_time']:.2f}, left at {to_str}")
        else:
            lines.append(f"  {eid}: no moves recorded")

    lines.append("\n=== END OF WORLD STATE DUMP ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chat(client: Any, **kwargs: Any) -> Any:
    """Wrapper around client.chat.completions.create with exponential backoff."""
    from openai import RateLimitError

    delay = 5.0
    for attempt in range(6):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == 5:
                raise
            print(f"  [rate limit] waiting {delay:.0f}s before retry ({attempt + 1}/5)...")
            time.sleep(delay)
            delay = min(delay * 2, 60.0)


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def run_blind(client: Any, model: str, question: str) -> tuple[str, float]:
    """Ask the LLM with no world data whatsoever. Returns (answer, latency_s)."""
    t0 = time.perf_counter()
    response = _chat(client, model=model, messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ])
    return response.choices[0].message.content or "", time.perf_counter() - t0


def run_context(client: Any, model: str, context: str, question: str) -> tuple[str, float]:
    """Ask the LLM with the full world state dump in the prompt. Returns (answer, latency_s)."""
    prompt = (
        f"{context}\n\n"
        "Use ONLY the information above to answer the following question.\n\n"
        f"Question: {question}"
    )
    t0 = time.perf_counter()
    response = _chat(client, model=model, messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    return response.choices[0].message.content or "", time.perf_counter() - t0


def run_graph(agent: OpenAIToolAgent, question: str) -> tuple[str, float]:
    """Ask the LLM using MCP tools backed by Neo4j. Returns (answer, latency_s)."""
    t0 = time.perf_counter()
    response = agent.run_with_tools(question)
    return response.answer, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You are a strict factual judge. "
    "You will be given a question, a ground truth answer, and a candidate answer. "
    "Decide whether the candidate answer is correct.\n\n"
    "Rules:\n"
    "- Ignore differences in capitalisation, punctuation, and word order for lists.\n"
    "- A candidate that names a superset of the correct items in a list is WRONG.\n"
    "- A candidate that names a subset of the correct items in a list is WRONG.\n"
    "- Partial credit does not exist — the answer is either correct (1) or wrong (0).\n\n"
    "Respond with JSON only, in the format:\n"
    '  {"correct": true, "reasoning": "one sentence explanation"}'
)


def judge(
    client: Any,
    model: str,
    question: str,
    ground_truth: str,
    candidate: str,
) -> dict[str, Any]:
    """Return {correct: bool, reasoning: str}."""
    prompt = (
        f"Question: {question}\n"
        f"Ground truth: {ground_truth}\n"
        f"Candidate answer: {candidate}"
    )
    response = _chat(client, model=model, messages=[
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": prompt},
    ], response_format={"type": "json_object"})
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"correct": False, "reasoning": f"judge parse error: {raw}"}
    return parsed


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def _truncate(s: str, n: int = 55) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


def print_results_table(results: list[dict[str, Any]]) -> None:
    # Columns: ID, Question, Ground Truth, Blind (pass+ms), Context (pass+ms), Graph (pass+ms)
    col_w = [6, 38, 28, 14, 14, 14]
    header = ["ID", "Question", "Ground Truth", "Blind", "Context", "Graph"]
    sep = "  ".join("-" * w for w in col_w)

    print()
    print("  ".join(h.ljust(w) for h, w in zip(header, col_w)))
    print(sep)

    totals   = {"blind": 0, "context": 0, "graph": 0}
    lat_sums = {"blind": 0.0, "context": 0.0, "graph": 0.0}

    for r in results:
        blind_ok   = r["blind"]["correct"]
        context_ok = r["context"]["correct"]
        graph_ok   = r["graph"]["correct"]

        totals["blind"]   += int(blind_ok)
        totals["context"] += int(context_ok)
        totals["graph"]   += int(graph_ok)

        lat_sums["blind"]   += r["blind"]["latency_s"]
        lat_sums["context"] += r["context"]["latency_s"]
        lat_sums["graph"]   += r["graph"]["latency_s"]

        def cell(ok: bool, latency: float) -> str:
            mark = "PASS" if ok else "FAIL"
            return f"{mark} ({latency * 1000:.0f}ms)"

        row = [
            r["id"],
            _truncate(r["question"], col_w[1]),
            _truncate(r["ground_truth"], col_w[2]),
            cell(blind_ok,   r["blind"]["latency_s"]),
            cell(context_ok, r["context"]["latency_s"]),
            cell(graph_ok,   r["graph"]["latency_s"]),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(row, col_w)))

    print(sep)
    n = len(results)

    def avg_ms(key: str) -> str:
        return f"avg {lat_sums[key] / n * 1000:.0f}ms"

    summary = [
        "TOTAL",
        "",
        "",
        f"{totals['blind']}/{n}  {avg_ms('blind')}",
        f"{totals['context']}/{n}  {avg_ms('context')}",
        f"{totals['graph']}/{n}  {avg_ms('graph')}",
    ]
    print("  ".join(v.ljust(w) for v, w in zip(summary, col_w)))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ChronosGraph benchmark")
    parser.add_argument("--model",       default="gpt-4.1",  help="Model for all three agent modes")
    parser.add_argument("--judge-model", default="gpt-4.1",  help="Model for the LLM judge")
    parser.add_argument("--out",         default="benchmark/results.json", help="Output JSON path")
    parser.add_argument(
        "--neo4j-password", default=NEO4J_PASSWORD,
        help="Neo4j password (default: testpassword)",
    )
    parser.add_argument(
        "--mega", action="store_true",
        help="Run MegaEpisode (6 objects, 61 steps) instead of ComplexEpisode (2 objects, 27 steps)",
    )
    args = parser.parse_args(argv)

    # ---- OpenAI client ----
    try:
        from openai import OpenAI  # type: ignore[import]
    except ModuleNotFoundError:
        print("ERROR: openai is not installed.  pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()

    # ---- Neo4j + bootstrap ----
    print("Connecting to Neo4j ...", flush=True)
    neo4j_graph = Neo4jGraph(NEO4J_URI, NEO4J_USER, args.neo4j_password)
    neo4j_graph.connect()

    # Clear any stale data from previous runs so INSIDE relationships don't accumulate
    print("Clearing previous graph data ...", flush=True)
    neo4j_graph.run_cypher("MATCH (n) DETACH DELETE n", {})

    episode_label = "mega" if args.mega else "complex"
    print(f"Bootstrapping world ({episode_label} episode) ...", flush=True)
    result = bootstrap_world(neo4j_graph=neo4j_graph, use_mega_episode=args.mega)
    world_engine: WorldStateEngine = result if isinstance(result, WorldStateEngine) else result[0]

    graph_api = GraphQueryAPI(neo4j_graph)
    world_api  = WorldQueryAPI(world_engine)

    # ---- Build graph agent ----
    system_prompt = SYSTEM_PROMPT_MEGA if args.mega else SYSTEM_PROMPT_COMPLEX
    registry = build_tool_registry(world_api, graph_api=graph_api)
    graph_agent = OpenAIToolAgent(registry, model=args.model, system_prompt=system_prompt)

    # ---- Build context string (used by context-stuffed mode) ----
    print("Building world context dump ...", flush=True)
    context = build_context(graph_api)

    questions = MEGA_QUESTIONS if args.mega else QUESTIONS
    print(f"\nRunning {len(questions)} questions across 3 modes ({episode_label} episode) ...\n")

    all_results: list[dict[str, Any]] = []

    for q in questions:
        ground_truth = q.ground_truth(graph_api)
        print(f"[{q.id}] {q.question}")
        print(f"       ground_truth = {ground_truth}")

        # -- Blind --
        blind_answer, blind_latency = run_blind(client, args.model, q.question)
        blind_score  = judge(client, args.judge_model, q.question, ground_truth, blind_answer)
        blind_mark   = "PASS" if blind_score["correct"] else "FAIL"
        print(f"       blind:   {blind_mark} ({blind_latency*1000:.0f}ms)  | {_truncate(blind_answer, 50)}")

        # -- Context --
        ctx_answer, ctx_latency = run_context(client, args.model, context, q.question)
        ctx_score  = judge(client, args.judge_model, q.question, ground_truth, ctx_answer)
        ctx_mark   = "PASS" if ctx_score["correct"] else "FAIL"
        print(f"       context: {ctx_mark} ({ctx_latency*1000:.0f}ms)  | {_truncate(ctx_answer, 50)}")

        # -- Graph --
        graph_answer, graph_latency = run_graph(graph_agent, q.question)
        graph_score  = judge(client, args.judge_model, q.question, ground_truth, graph_answer)
        graph_mark   = "PASS" if graph_score["correct"] else "FAIL"
        print(f"       graph:   {graph_mark} ({graph_latency*1000:.0f}ms)  | {_truncate(graph_answer, 50)}")
        print()
        time.sleep(2)  # avoid TPM rate limit between questions

        all_results.append(
            {
                "id":           q.id,
                "question":     q.question,
                "category":     q.category,
                "ground_truth": ground_truth,
                "blind": {
                    "answer":    blind_answer,
                    "correct":   blind_score["correct"],
                    "reasoning": blind_score.get("reasoning", ""),
                    "latency_s": round(blind_latency, 3),
                },
                "context": {
                    "answer":    ctx_answer,
                    "correct":   ctx_score["correct"],
                    "reasoning": ctx_score.get("reasoning", ""),
                    "latency_s": round(ctx_latency, 3),
                },
                "graph": {
                    "answer":    graph_answer,
                    "correct":   graph_score["correct"],
                    "reasoning": graph_score.get("reasoning", ""),
                    "latency_s": round(graph_latency, 3),
                },
            }
        )

    # ---- Summary table ----
    print_results_table(all_results)

    # ---- Save JSON ----
    output = {
        "run_at":      datetime.now().isoformat(),
        "episode":     episode_label,
        "model":       args.model,
        "judge_model": args.judge_model,
        "results":     all_results,
    }
    with open(args.out, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"Results saved to {args.out}")

    neo4j_graph.disconnect()


if __name__ == "__main__":
    main()
