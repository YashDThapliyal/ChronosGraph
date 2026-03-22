"""
Multi-object, multi-container episode designed to stress-test LLM memory.

Episode narrative (27 steps)
-----------------------------
Two objects move through multiple containers with distractor rotations
in between.  The final state is intentionally deceptive:

  keys_001 : table_01 -> counter_01 -> drawer_01 -> counter_01
  card_001 : [origin] -> drawer_01  (stays in drawer the whole second half)

A baseline LLM asked "what is in the drawer?" will likely say "the keys"
because they were placed there more recently in the action sequence.
The knowledge graph answers correctly: only card_001 is in the drawer.

Temporal questions that require the graph
-----------------------------------------
  "Where are the keys right now?"              get_current_parent("keys_001")
  "Where were the keys at t=1.5?"              get_parent_at("keys_001", 1.5)
  "What is currently in the drawer?"           find_entities_in_container("drawer_01")
  "List every container the keys have been in" get_containment_history("keys_001")

AI2-THOR constraints respected
-------------------------------
  - Agent holds at most one object at a time
  - PutObject only targets counter_01 and drawer_01 (both confirmed working)
  - All interactions use forceAction=True to bypass proximity checks
"""

from __future__ import annotations

from typing import Any

from simulator import AI2ThorSimulator
from simulator.models import Observation

from .base_episode import Episode


class ComplexEpisode(Episode):
    """
    27-step scripted episode with two objects moving through multiple containers.

    If the credit card cannot be resolved, card-related steps fall back to
    Pass so the episode still runs without errors.
    """

    def __init__(self) -> None:
        self.step_index = 0
        self.actions: list[dict[str, Any]] = []
        self.done = False

        self._keys_id:    str | None = None
        self._card_id:    str | None = None
        self._drawer_id:  str | None = None
        self._counter_id: str | None = None

    # ------------------------------------------------------------------ #
    # Episode interface
    # ------------------------------------------------------------------ #

    def initialize(self, simulator: AI2ThorSimulator) -> None:
        self.step_index = 0
        self.done = False

        controller = self._get_controller(simulator)
        event = controller.step(action="Pass")
        objects: list[dict[str, Any]] = event.metadata.get("objects", [])

        # Resolve AI2-THOR objectIds
        self._keys_id    = self._resolve_keys(simulator, objects)
        self._drawer_id  = self._resolve_drawer(objects)
        self._counter_id = self._resolve_countertop(objects)
        self._card_id    = self._resolve_card(objects, exclude=self._keys_id)

        # Register aliases so the simulator tracks them by friendly name
        if self._keys_id:
            simulator._id_aliases[self._keys_id]    = "keys_001"
        if self._drawer_id:
            simulator._id_aliases[self._drawer_id]  = "drawer_01"
        if self._counter_id:
            simulator._id_aliases[self._counter_id] = "counter_01"
        if self._card_id:
            simulator._id_aliases[self._card_id]    = "card_001"

        self.actions = self._build_action_sequence()

    def step(self, simulator: AI2ThorSimulator) -> Observation:
        """Execute one scripted action and return the resulting observation."""
        if self.done:
            return simulator.get_observation()

        action = self.actions[self.step_index]
        controller = self._get_controller(simulator)
        event = controller.step(**action)

        simulator._frame_id += 1
        simulator._sim_time  = simulator._frame_id * simulator.timestep_seconds
        simulator._last_observation = simulator._extract_observation(event)

        self.step_index += 1
        self.done = self.step_index >= len(self.actions)
        return simulator.get_observation()

    def is_done(self) -> bool:
        return self.done

    # ------------------------------------------------------------------ #
    # Action sequence
    # ------------------------------------------------------------------ #

    def _build_action_sequence(self) -> list[dict[str, Any]]:
        keys    = self._keys_id    or "keys_001"
        drawer  = self._drawer_id  or "drawer_01"
        counter = self._counter_id or "counter_01"
        card    = self._card_id
        noop    = {"action": "Pass"}

        def pickup(obj_id: str)  -> dict[str, Any]:
            return {"action": "PickupObject", "objectId": obj_id, "forceAction": True}

        def put(obj_id: str) -> dict[str, Any]:
            return {"action": "PutObject", "objectId": obj_id, "forceAction": True}

        def open_obj(obj_id: str) -> dict[str, Any]:
            return {"action": "OpenObject", "objectId": obj_id, "forceAction": True}

        def close_obj(obj_id: str) -> dict[str, Any]:
            return {"action": "CloseObject", "objectId": obj_id, "forceAction": True}

        return [
            # ---- Phase 1: initial observation (0-2) ----
            noop,
            {"action": "RotateRight"},
            {"action": "MoveAhead"},

            # ---- Phase 2: keys table -> counter (3-5) ----
            pickup(keys),
            put(counter),                           # keys_001: table_01 -> counter_01
            noop,

            # ---- Phase 3: card [origin] -> drawer (6-9) ----
            # Agent holds nothing here. Card goes straight into the drawer.
            pickup(card) if card else noop,
            open_obj(drawer),
            put(drawer) if card else noop,          # card_001: origin -> drawer_01
            close_obj(drawer),

            # ---- Phase 4: distractor movements (10-12) ----
            {"action": "RotateLeft"},
            {"action": "RotateRight"},
            noop,

            # ---- Phase 5: keys counter -> drawer (13-16) ----
            # Now both keys and card end up in the drawer together.
            pickup(keys),
            open_obj(drawer),                       # card_001 is inside
            put(drawer),                            # keys_001: counter_01 -> drawer_01
            close_obj(drawer),

            # ---- Phase 6: distractor rotations (17-20) ----
            noop,
            {"action": "RotateRight"},
            {"action": "RotateLeft"},
            noop,

            # ---- Phase 7: DECEPTIVE move — keys leave the drawer (21-24) ----
            # LLM will likely still think keys are in the drawer.
            # Graph correctly shows keys moved back to counter.
            open_obj(drawer),
            pickup(keys),                           # keys_001: drawer_01 -> agent
            close_obj(drawer),                      # card_001 stays in drawer
            put(counter),                           # keys_001: agent -> counter_01

            # ---- Phase 8: final observation (25-26) ----
            {"action": "RotateLeft"},
            noop,
        ]

    # ------------------------------------------------------------------ #
    # Object resolution helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_controller(simulator: AI2ThorSimulator) -> Any:
        if simulator._controller is None:
            raise RuntimeError("Simulator not initialized.")
        return simulator._controller

    @staticmethod
    def _resolve_keys(
        simulator: AI2ThorSimulator,
        objects: list[dict[str, Any]],
    ) -> str | None:
        if simulator._key_object_id:
            return simulator._key_object_id
        for obj_id, alias in simulator._id_aliases.items():
            if alias == "keys_001":
                return obj_id
        for obj in objects:
            if obj.get("objectType") in {"Key", "KeyChain"}:
                return str(obj["objectId"])
        for obj in objects:
            if obj.get("pickupable"):
                return str(obj["objectId"])
        return None

    @staticmethod
    def _resolve_drawer(objects: list[dict[str, Any]]) -> str | None:
        for obj in objects:
            if str(obj.get("objectId")) == "drawer_01":
                return "drawer_01"
        for obj in objects:
            if "Drawer" in str(obj.get("objectType", "")) and obj.get("visible"):
                return str(obj["objectId"])
        for obj in objects:
            if "Drawer" in str(obj.get("objectType", "")):
                return str(obj["objectId"])
        return None

    @staticmethod
    def _resolve_countertop(objects: list[dict[str, Any]]) -> str | None:
        for obj in objects:
            if "CounterTop" in str(obj.get("objectType", "")) and obj.get("visible"):
                return str(obj["objectId"])
        for obj in objects:
            if "CounterTop" in str(obj.get("objectType", "")):
                return str(obj["objectId"])
        return None

    @staticmethod
    def _resolve_card(
        objects: list[dict[str, Any]],
        exclude: str | None,
    ) -> str | None:
        """Find a second pickupable object (prefer CreditCard)."""
        for obj in objects:
            if obj.get("objectType") == "CreditCard" and str(obj["objectId"]) != exclude:
                return str(obj["objectId"])
        for obj in objects:
            if (
                obj.get("pickupable")
                and str(obj["objectId"]) != exclude
                and obj.get("objectType") not in {"Key", "KeyChain"}
            ):
                return str(obj["objectId"])
        return None
