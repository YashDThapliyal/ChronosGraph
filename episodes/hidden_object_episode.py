"""Deterministic hidden-object episode for Phase 3 demos."""

from __future__ import annotations

from typing import Any

from simulator import AI2ThorSimulator
from simulator.models import Observation

from .base_episode import Episode


class HiddenObjectEpisode(Episode):
    """Scripted episode: hide keys in a drawer, rotate away, rotate back."""

    def __init__(self) -> None:
        self.step_index = 0
        self.actions: list[dict[str, Any]] = []
        self.done = False
        self._drawer_object_id: str | None = None
        self._keys_object_id: str | None = None

    def initialize(self, simulator: AI2ThorSimulator) -> None:
        """Resolve object ids and create deterministic action sequence."""
        self.step_index = 0
        self.done = False

        controller = self._controller(simulator)
        event = controller.step(action="Pass")
        objects: list[dict[str, Any]] = event.metadata.get("objects", [])

        self._keys_object_id = self._resolve_keys_id(simulator, objects)
        self._drawer_object_id = self._resolve_drawer_id(objects)

        if self._keys_object_id is not None:
            simulator._id_aliases[self._keys_object_id] = "keys_001"
        if self._drawer_object_id is not None:
            simulator._id_aliases[self._drawer_object_id] = "drawer_01"

        pickup_object_id = self._keys_object_id or "keys_001"
        drawer_object_id = self._drawer_object_id or "drawer_01"

        self.actions = [
            {"action": "Pass"},
            {"action": "RotateRight"},
            {"action": "MoveAhead"},
            {"action": "PickupObject", "objectId": pickup_object_id, "forceAction": True},
            {"action": "OpenObject", "objectId": drawer_object_id, "forceAction": True},
            {
                "action": "PutObject",
                "objectId": drawer_object_id,
                "forceAction": True,
            },
            {"action": "RotateLeft"},
            {"action": "RotateLeft"},
        ]

    def step(self, simulator: AI2ThorSimulator) -> Observation:
        """Execute one scripted action and return updated observation."""
        if self.done:
            return simulator.get_observation()

        action = self.actions[self.step_index]
        controller = self._controller(simulator)
        event = controller.step(**action)

        simulator._frame_id += 1
        simulator._sim_time = simulator._frame_id * simulator.timestep_seconds
        simulator._last_observation = simulator._extract_observation(event)

        self.step_index += 1
        self.done = self.step_index >= len(self.actions)
        return simulator.get_observation()

    def is_done(self) -> bool:
        return self.done

    @staticmethod
    def _controller(simulator: AI2ThorSimulator) -> Any:
        controller = simulator._controller
        if controller is None:
            raise RuntimeError("Simulator controller is unavailable. Call initialize() first.")
        return controller

    @staticmethod
    def _resolve_keys_id(
        simulator: AI2ThorSimulator,
        objects: list[dict[str, Any]],
    ) -> str | None:
        if simulator._key_object_id is not None:
            return simulator._key_object_id
        for object_id, alias in simulator._id_aliases.items():
            if alias == "keys_001":
                return object_id
        for obj in objects:
            if obj.get("objectType") in {"Key", "KeyChain"}:
                return str(obj.get("objectId"))
        for obj in objects:
            if bool(obj.get("pickupable")):
                return str(obj.get("objectId"))
        return None

    @staticmethod
    def _resolve_drawer_id(objects: list[dict[str, Any]]) -> str | None:
        for obj in objects:
            if str(obj.get("objectId")) == "drawer_01":
                return "drawer_01"
        for obj in objects:
            object_type = str(obj.get("objectType", ""))
            if "Drawer" in object_type and bool(obj.get("visible", False)):
                return str(obj.get("objectId"))
        for obj in objects:
            object_type = str(obj.get("objectType", ""))
            if "Drawer" in object_type:
                return str(obj.get("objectId"))
        return None
