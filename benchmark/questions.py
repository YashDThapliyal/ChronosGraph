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
# Helper — number of containers an entity passed through
# ---------------------------------------------------------------------------

def _all_co_located_containers(api: "GraphQueryAPI", eid_a: str, eid_b: str) -> list[str]:
    """
    Return all containers where eid_a and eid_b were present at the same time,
    in chronological order. Uses midpoint sampling across both entities' periods.
    """
    found: list[str] = []
    seen: set[str] = set()

    hist_a = api.get_containment_history(eid_a)
    hist_b = api.get_containment_history(eid_b)

    for entry_a in hist_a:
        t_start_a = entry_a["from_time"]
        t_end_a   = entry_a["to_time"]  # None = open

        for entry_b in hist_b:
            if entry_a["container"] != entry_b["container"]:
                continue
            t_start_b = entry_b["from_time"]
            t_end_b   = entry_b["to_time"]  # None = open

            # Compute overlap interval
            overlap_start = max(t_start_a, t_start_b)
            overlap_end_a = t_end_a if t_end_a is not None else float("inf")
            overlap_end_b = t_end_b if t_end_b is not None else float("inf")
            overlap_end   = min(overlap_end_a, overlap_end_b)

            if overlap_start < overlap_end:
                container = entry_a["container"]
                if container not in seen:
                    seen.add(container)
                    found.append(container)

    return found if found else ["never"]


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


# ---------------------------------------------------------------------------
# Mega episode question bank (14 questions, 6 objects, designed to break
# context stuffing — hardcoded entity IDs from MegaEpisode aliases)
# ---------------------------------------------------------------------------

MEGA_QUESTIONS: list[Question] = [
    # --- Tier 1: current state — all deceptive ---
    Question(
        id="m01",
        question="Where are the keys (keys_001) right now?",
        category="current_location",
        hint="keys end in fridge_01 — most LLMs guess counter or drawer",
        ground_truth_fn=lambda api: api.where_is("keys_001")["parent"],
    ),
    Question(
        id="m02",
        question="Where is card_001 right now?",
        category="current_location",
        hint="card ends on counter_01 — LLMs may say fridge since it was there",
        ground_truth_fn=lambda api: api.where_is("card_001")["parent"],
    ),
    Question(
        id="m03",
        question="What objects are currently inside drawer_01?",
        category="container_contents",
        hint="drawer ends with mug + spatula — LLMs say keys/card/knife",
        ground_truth_fn=lambda api: [e["entity_id"] for e in api.whats_inside("drawer_01")] or ["nothing"],
    ),
    Question(
        id="m04",
        question="What objects are currently inside fridge_01?",
        category="container_contents",
        hint="fridge ends with only keys_001 — LLMs say card since it was there longer",
        ground_truth_fn=lambda api: [e["entity_id"] for e in api.whats_inside("fridge_01")] or ["nothing"],
    ),
    Question(
        id="m05",
        question="What objects are currently on counter_01?",
        category="container_contents",
        hint="counter ends with card_001 and knife_001",
        ground_truth_fn=lambda api: sorted([e["entity_id"] for e in api.whats_inside("counter_01")]) or ["nothing"],
    ),

    # --- Tier 2: historical point-in-time ---
    Question(
        id="m06",
        question="Where was knife_001 at t=2.5?",
        category="historical_location",
        hint="knife was in drawer_01 during the middle phase",
        ground_truth_fn=lambda api: api.where_was("knife_001", 2.5)["parent"],
    ),
    Question(
        id="m07",
        question="What was inside drawer_01 at t=1.5?",
        category="historical_contents",
        hint="at t=1.5 both keys and card are in drawer",
        ground_truth_fn=lambda api: _entities_in_container_at(api, "drawer_01", 1.5),
    ),
    Question(
        id="m08",
        question="What was inside fridge_01 at t=3.5?",
        category="historical_contents",
        hint="at t=3.5 card is in fridge but keys have not arrived yet",
        ground_truth_fn=lambda api: _entities_in_container_at(api, "fridge_01", 3.5),
    ),

    # --- Tier 3: full history ---
    Question(
        id="m09",
        question="List every container keys_001 has been in, in order.",
        category="full_history",
        hint="keys: counter -> drawer -> counter -> fridge (4 stops)",
        ground_truth_fn=lambda api: [h["container"] for h in api.get_containment_history("keys_001")],
    ),
    Question(
        id="m10",
        question="List every container card_001 has been in, in order.",
        category="full_history",
        hint="card: counter -> drawer -> fridge -> counter (4 stops)",
        ground_truth_fn=lambda api: [h["container"] for h in api.get_containment_history("card_001")],
    ),
    Question(
        id="m11",
        question="List every container knife_001 has been in, in order.",
        category="full_history",
        hint="knife: counter -> drawer -> counter (3 stops)",
        ground_truth_fn=lambda api: [h["container"] for h in api.get_containment_history("knife_001")],
    ),

    # --- Tier 4: cross-entity reasoning ---
    Question(
        id="m12",
        question="How many different containers has keys_001 been in total?",
        category="aggregation",
        hint="keys visits 3 distinct containers across 4 moves",
        ground_truth_fn=lambda api: len({h["container"] for h in api.get_containment_history("keys_001")}),
    ),
    Question(
        id="m13",
        question="List every container where keys_001 and card_001 were present at the same time.",
        category="co_location",
        hint="they overlapped in drawer_01 (keys in first, card entered while keys still there) and fridge_01",
        ground_truth_fn=lambda api: _all_co_located_containers(api, "keys_001", "card_001"),
    ),
    Question(
        id="m14",
        question="Which objects have ever been inside fridge_01?",
        category="container_history",
        hint="requires the find_entities_ever_in_container tool — card, egg, and keys all visited fridge",
        ground_truth_fn=lambda api: sorted([e["entity_id"] for e in api.who_ever_was_in("fridge_01")]) or ["nothing"],
    ),
]
