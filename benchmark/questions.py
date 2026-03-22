"""
Benchmark question definitions for ChronosGraph.

Each question has:
  - A natural-language question posed to the agent
  - A ground_truth_fn that derives the correct answer from the graph at runtime
  - A category describing what capability it tests

Ground truths are derived from the live graph so the benchmark stays correct
if the episode changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from query_api.graph_query_api import GraphQueryAPI


@dataclass
class Question:
    id: str
    question: str
    category: str
    hint: str
    ground_truth_fn: Callable[["GraphQueryAPI"], Any]

    def ground_truth(self, api: "GraphQueryAPI") -> str:
        result = self.ground_truth_fn(api)
        if isinstance(result, list):
            return ", ".join(str(x) for x in result)
        return str(result)


# ---------------------------------------------------------------------------
# Helper functions for multi-step ground truth derivation
# ---------------------------------------------------------------------------

def _entities_in_container_at(api: "GraphQueryAPI", container_id: str, timestamp: float) -> list[str]:
    """All entities whose parent was container_id at the given timestamp."""
    rows = api._graph.run_cypher(
        """
        MATCH (e:Entity)-[r:INSIDE]->(c:Entity {entity_id: $cid})
        WHERE r.from_time <= $t
          AND (r.to_time IS NULL OR r.to_time > $t)
        RETURN e.entity_id AS eid
        ORDER BY e.entity_id
        """,
        {"cid": container_id, "t": timestamp},
    )
    return [row["eid"] for row in rows] if rows else ["nothing"]


def _same_start_end(api: "GraphQueryAPI", entity_id: str) -> str:
    history = api.get_containment_history(entity_id)
    if not history:
        return "unknown"
    first = history[0]["container"]
    last  = history[-1]["container"]
    if first == last:
        return f"yes, both {first}"
    return f"no, started in {first}, ended in {last}"


def _container_before(api: "GraphQueryAPI", entity_id: str, target: str) -> str:
    history = api.get_containment_history(entity_id)
    for i, entry in enumerate(history):
        if entry["container"] == target and i > 0:
            return history[i - 1]["container"]
    return "none"


# ---------------------------------------------------------------------------
# Question bank (10 questions, increasing difficulty)
# ---------------------------------------------------------------------------

QUESTIONS: list[Question] = [
    # --- Tier 1: current state (simplest) ---
    Question(
        id="q01",
        question="Where are the keys (keys_001) right now?",
        category="current_location",
        hint="get_current_parent — easiest possible query",
        ground_truth_fn=lambda api: api.where_is("keys_001")["parent"],
    ),
    Question(
        id="q02",
        question="What objects are currently inside drawer_01?",
        category="container_contents",
        hint="find_entities_in_container — requires reverse graph traversal",
        ground_truth_fn=lambda api: [e["entity_id"] for e in api.whats_inside("drawer_01")] or ["nothing"],
    ),
    Question(
        id="q03",
        question="Where is card_001 right now?",
        category="current_location",
        hint="get_current_parent for second object",
        ground_truth_fn=lambda api: api.where_is("card_001")["parent"],
    ),

    # --- Tier 2: historical point-in-time ---
    Question(
        id="q04",
        question="Where were the keys at t=2.0?",
        category="historical_location",
        hint="get_parent_at — keys were in drawer at this time",
        ground_truth_fn=lambda api: api.where_was("keys_001", 2.0)["parent"],
    ),
    Question(
        id="q05",
        question="Where were the keys at t=0.6?",
        category="historical_location",
        hint="get_parent_at — earlier timestep, keys were on counter",
        ground_truth_fn=lambda api: api.where_was("keys_001", 0.6)["parent"],
    ),
    Question(
        id="q06",
        question="Which objects were inside drawer_01 at t=2.0?",
        category="historical_contents",
        hint="multi-entity temporal query — requires checking history of multiple entities",
        ground_truth_fn=lambda api: _entities_in_container_at(api, "drawer_01", 2.0),
    ),

    # --- Tier 3: full history ---
    Question(
        id="q07",
        question="List every container the keys have been in, in chronological order.",
        category="full_history",
        hint="get_containment_history — 4-stop chain",
        ground_truth_fn=lambda api: [h["container"] for h in api.get_containment_history("keys_001")],
    ),
    Question(
        id="q08",
        question="List every container card_001 has been in, in chronological order.",
        category="full_history",
        hint="get_containment_history for the second object",
        ground_truth_fn=lambda api: [h["container"] for h in api.get_containment_history("card_001")],
    ),

    # --- Tier 4: reasoning over history ---
    Question(
        id="q09",
        question="Did the keys end the episode in the same container they started in?",
        category="comparison",
        hint="requires comparing first and last containment entries",
        ground_truth_fn=lambda api: _same_start_end(api, "keys_001"),
    ),
    Question(
        id="q10",
        question="What was the last container the keys were in before they entered drawer_01?",
        category="sequential_history",
        hint="requires reading ordered containment history and finding the predecessor",
        ground_truth_fn=lambda api: _container_before(api, "keys_001", "drawer_01"),
    ),
]
