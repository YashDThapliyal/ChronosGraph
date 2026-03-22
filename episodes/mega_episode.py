"""
Large-scale multi-object episode designed to break context-stuffing baselines.

Episode narrative (61 steps)
------------------------------
Six objects move through three containers across four distinct phases, with
deliberate distractor rotations between each phase. The final state is
maximally deceptive: every object has been in at least two containers, the
two most attention-grabbing objects (keys and card) end in unexpected places,
and the drawer's final contents are completely different from anything the
agent last observed going in.

Object journeys
---------------
  keys_001    : counter -> drawer -> counter -> fridge
  card_001    : counter -> drawer -> fridge  -> counter
  knife_001   : counter -> drawer -> counter (stays there)
  mug_001     : counter -> drawer            (stays there)
  spatula_001 : counter -> drawer            (stays there)
  apple_001   : (not moved — acts as a stable reference object)

Final state
-----------
  fridge_01  : keys_001
  counter_01 : card_001, knife_001
  drawer_01  : mug_001, spatula_001

What context-stuffing gets wrong
---------------------------------
  "Where are the keys?"
      LLM: counter or drawer (both appear prominently in the sequence)
      Graph: fridge_01

  "What is in the fridge?"
      LLM: card (it was there — but it was moved out)
      Graph: keys_001

  "What is in the drawer?"
      LLM: keys, card, knife (all went in at various points)
      Graph: mug_001, spatula_001

  "What is in the drawer right now vs at t=2.0?"
      LLM: cannot distinguish
      Graph: different answers via Cypher range queries

At ~6 tracked objects and ~20 containment events, the context dump is several
hundred lines. With 20+ objects it would overflow entirely.

AI2-THOR constraints
--------------------
  - forceAction=True bypasses proximity checks
  - PUT targets: counter_01, drawer_01, fridge_01 (all confirmed receptacles)
  - Agent holds at most one object at a time
  - Fridge and drawer require Open/Close bracketing
"""

from __future__ import annotations

from typing import Any

from simulator import AI2ThorSimulator
from simulator.models import Observation

from .base_episode import Episode


class MegaEpisode(Episode):
    """
    61-step scripted episode with 6 objects across 3 containers.

    Designed to overwhelm context-stuffing baselines: the final state of
    every high-attention object (keys, card, knife) contradicts what the
    LLM would predict from naive sequence reading.
    """

    def __init__(self) -> None:
        self.step_index = 0
        self.actions: list[dict[str, Any]] = []
        self.done = False

        self._keys_id:     str | None = None
        self._card_id:     str | None = None
        self._knife_id:    str | None = None
        self._mug_id:      str | None = None
        self._spatula_id:  str | None = None
        self._drawer_id:   str | None = None
        self._counter_id:  str | None = None
        self._fridge_id:   str | None = None

    # ------------------------------------------------------------------ #
    # Episode interface
    # ------------------------------------------------------------------ #

    def initialize(self, simulator: AI2ThorSimulator) -> None:
        self.step_index = 0
        self.done = False

        controller = self._get_controller(simulator)
        event = controller.step(action="Pass")
        objects: list[dict[str, Any]] = event.metadata.get("objects", [])

        # Resolve AI2-THOR object IDs
        excluded: list[str] = []

        self._keys_id = self._resolve_by_type(objects, {"Key", "KeyChain"}, excluded)
        if self._keys_id:
            excluded.append(self._keys_id)

        self._card_id = self._resolve_by_type(objects, {"CreditCard"}, excluded)
        if self._card_id:
            excluded.append(self._card_id)

        self._knife_id = self._resolve_by_type(objects, {"Knife", "ButterKnife"}, excluded)
        if self._knife_id:
            excluded.append(self._knife_id)

        self._mug_id = self._resolve_by_type(objects, {"Mug", "Cup"}, excluded)
        if self._mug_id:
            excluded.append(self._mug_id)

        self._spatula_id = self._resolve_by_type(objects, {"Spatula"}, excluded)
        if self._spatula_id:
            excluded.append(self._spatula_id)

        self._drawer_id  = self._resolve_container(objects, "Drawer")
        self._counter_id = self._resolve_container(objects, "CounterTop")
        self._fridge_id  = self._resolve_container(objects, "Fridge")

        # Register aliases
        aliases = {
            self._keys_id:    "keys_001",
            self._card_id:    "card_001",
            self._knife_id:   "knife_001",
            self._mug_id:     "mug_001",
            self._spatula_id: "spatula_001",
            self._drawer_id:  "drawer_01",
            self._counter_id: "counter_01",
            self._fridge_id:  "fridge_01",
        }
        for obj_id, alias in aliases.items():
            if obj_id:
                simulator._id_aliases[obj_id] = alias

        self.actions = self._build_action_sequence()

    def step(self, simulator: AI2ThorSimulator) -> Observation:
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
        card    = self._card_id    or "card_001"
        knife   = self._knife_id   or "knife_001"
        mug     = self._mug_id     or "mug_001"
        spatula = self._spatula_id or "spatula_001"
        drawer  = self._drawer_id  or "drawer_01"
        counter = self._counter_id or "counter_01"
        fridge  = self._fridge_id  or "fridge_01"

        noop = {"action": "Pass"}

        def pickup(obj_id: str) -> dict[str, Any]:
            return {"action": "PickupObject", "objectId": obj_id, "forceAction": True}

        def put(receptacle_id: str) -> dict[str, Any]:
            return {"action": "PutObject", "objectId": receptacle_id, "forceAction": True}

        def open_obj(obj_id: str) -> dict[str, Any]:
            return {"action": "OpenObject", "objectId": obj_id, "forceAction": True}

        def close_obj(obj_id: str) -> dict[str, Any]:
            return {"action": "CloseObject", "objectId": obj_id, "forceAction": True}

        return [
            # ---- Phase 1: initial observation (0-2) ----
            noop,
            {"action": "RotateRight"},
            {"action": "MoveAhead"},

            # ---- Phase 2: keys -> drawer (3-6) ----
            # keys_001: counter -> drawer_01
            pickup(keys),
            open_obj(drawer),
            put(drawer),
            close_obj(drawer),

            # ---- Phase 3: card -> drawer (7-10) ----
            # card_001: counter -> drawer_01  (now drawer has keys + card)
            pickup(card),
            open_obj(drawer),
            put(drawer),
            close_obj(drawer),

            # ---- Phase 4: distractor (11-14) ----
            {"action": "RotateLeft"},
            {"action": "RotateRight"},
            noop,
            {"action": "MoveAhead"},

            # ---- Phase 5: keys drawer -> counter (15-18) ----
            # keys_001: drawer_01 -> counter_01
            # card_001 remains in drawer
            open_obj(drawer),
            pickup(keys),
            close_obj(drawer),
            put(counter),

            # ---- Phase 6: knife -> drawer (19-22) ----
            # knife_001: counter -> drawer_01
            pickup(knife),
            open_obj(drawer),
            put(drawer),
            close_obj(drawer),

            # ---- Phase 7: distractor (23-26) ----
            {"action": "RotateRight"},
            noop,
            {"action": "RotateLeft"},
            noop,

            # ---- Phase 8: card drawer -> fridge (27-32) ----
            # card_001: drawer_01 -> fridge_01
            open_obj(drawer),
            pickup(card),
            close_obj(drawer),
            open_obj(fridge),
            put(fridge),
            close_obj(fridge),

            # ---- Phase 9: knife drawer -> counter (33-36) ----
            # knife_001: drawer_01 -> counter_01
            open_obj(drawer),
            pickup(knife),
            close_obj(drawer),
            put(counter),

            # ---- Phase 10: mug -> drawer (37-40) ----
            # mug_001: counter -> drawer_01
            pickup(mug),
            open_obj(drawer),
            put(drawer),
            close_obj(drawer),

            # ---- Phase 11: distractor (41-44) ----
            noop,
            {"action": "RotateRight"},
            {"action": "RotateLeft"},
            noop,

            # ---- Phase 12: spatula -> drawer (45-48) ----
            # spatula_001: counter -> drawer_01
            pickup(spatula),
            open_obj(drawer),
            put(drawer),
            close_obj(drawer),

            # ---- Phase 13: DECEPTIVE — keys counter -> fridge (49-52) ----
            # keys_001: counter_01 -> fridge_01
            # LLM last heard about keys going into counter; now quietly moved to fridge
            pickup(keys),
            open_obj(fridge),
            put(fridge),
            close_obj(fridge),

            # ---- Phase 14: DECEPTIVE — card fridge -> counter (53-56) ----
            # card_001: fridge_01 -> counter_01
            # LLM last heard about card going into fridge; now quietly moved back to counter
            open_obj(fridge),
            pickup(card),
            close_obj(fridge),
            put(counter),

            # ---- Phase 15: final observation (57-60) ----
            {"action": "RotateLeft"},
            noop,
            {"action": "RotateRight"},
            noop,
        ]

    # ------------------------------------------------------------------ #
    # Object / container resolution helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_controller(simulator: AI2ThorSimulator) -> Any:
        if simulator._controller is None:
            raise RuntimeError("Simulator not initialized.")
        return simulator._controller

    @staticmethod
    def _resolve_by_type(
        objects: list[dict[str, Any]],
        types: set[str],
        exclude: list[str],
    ) -> str | None:
        """Return the first pickupable object matching one of the given types."""
        for obj in objects:
            oid = str(obj.get("objectId", ""))
            if obj.get("objectType") in types and oid not in exclude:
                return oid
        # Fallback: any pickupable not already claimed
        for obj in objects:
            oid = str(obj.get("objectId", ""))
            if obj.get("pickupable") and oid not in exclude:
                return oid
        return None

    @staticmethod
    def _resolve_container(
        objects: list[dict[str, Any]],
        container_type: str,
    ) -> str | None:
        """Return the first visible container of the given type, then any."""
        for obj in objects:
            if container_type in str(obj.get("objectType", "")) and obj.get("visible"):
                return str(obj["objectId"])
        for obj in objects:
            if container_type in str(obj.get("objectType", "")):
                return str(obj["objectId"])
        return None
