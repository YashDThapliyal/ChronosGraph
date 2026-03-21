"""
AI2-THOR simulator integration for ChronosGraph Phase 1.

This module is intentionally limited to world stepping and observation
extraction. It does not include memory logic, event detection, or beliefs.
"""

from __future__ import annotations

import math
from typing import Any

from .models import EntityObservation, Observation, Position
from .simulator_interface import SimulatorInterface

try:
    from ai2thor.controller import Controller
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    Controller = None  # type: ignore[assignment]


class AI2ThorSimulator(SimulatorInterface):
    """Concrete AI2-THOR simulator that emits structured observations."""

    def __init__(
        self,
        scene_name: str = "FloorPlan1",
        timestep_seconds: float = 0.1,
        width: int = 640,
        height: int = 480,
    ) -> None:
        self.scene_name = scene_name
        self.timestep_seconds = timestep_seconds
        self.width = width
        self.height = height

        self._controller: Controller | None = None
        self._frame_id = 0
        self._sim_time = 0.0
        self._done = False
        self._last_observation: Observation | None = None
        self._scripted_actions: list[dict[str, Any]] = []
        self._id_aliases: dict[str, str] = {}
        self._key_object_id: str | None = None

    def initialize(self) -> None:
        """Launch AI2-THOR, load a deterministic scene, and prepare the episode."""
        if Controller is None:
            raise RuntimeError(
                "AI2-THOR is not installed. Install it with: pip install ai2thor"
            )

        self.shutdown()
        self._controller = Controller(
            scene=self.scene_name,
            width=self.width,
            height=self.height,
            fieldOfView=90,
            snapToGrid=True,
            gridSize=0.25,
        )

        self._frame_id = 0
        self._sim_time = 0.0
        self._done = False
        self._last_observation = None
        self._scripted_actions = [
            {"action": "Pass"},
            {"action": "RotateRight", "degrees": 180},
            {"action": "Pass"},
        ]
        self._id_aliases = {}
        self._key_object_id = None

        self._prepare_key_visibility_demo()
        event = self._controller.step(action="Pass")
        self._last_observation = self._extract_observation(event)

    def step(self) -> Observation:
        """Advance one scripted step and return the resulting observation."""
        self._require_controller()

        if self._done:
            return self.get_observation()

        action_index = self._frame_id
        action = (
            self._scripted_actions[action_index]
            if action_index < len(self._scripted_actions)
            else {"action": "Pass"}
        )
        event = self._controller.step(**action)  # type: ignore[union-attr]

        self._frame_id += 1
        self._sim_time = self._frame_id * self.timestep_seconds
        self._last_observation = self._extract_observation(event)
        self._done = self._frame_id >= len(self._scripted_actions)
        return self._last_observation

    def get_observation(self) -> Observation:
        """Return the latest extracted observation."""
        if self._last_observation is None:
            raise RuntimeError("No observation available. Call initialize() first.")
        return self._last_observation

    def reset(self) -> None:
        """Reset by re-initializing the same deterministic scene."""
        self.initialize()

    def is_done(self) -> bool:
        """Return True when the scripted demo has finished."""
        return self._done

    def get_current_time(self) -> float:
        """Return current simulation time in seconds."""
        return self._sim_time

    def shutdown(self) -> None:
        """Stop the controller and release resources."""
        if self._controller is not None:
            self._controller.stop()
            self._controller = None

    def _prepare_key_visibility_demo(self) -> None:
        """
        Configure a deterministic setup where keys start visible on a table.

        If a key object is unavailable in the scene, the first pickupable object
        is used and aliased to keys_001 for demo consistency.
        """
        self._require_controller()
        event = self._controller.step(action="Pass")  # type: ignore[union-attr]
        objects: list[dict[str, Any]] = event.metadata.get("objects", [])

        table = self._find_first(
            objects,
            lambda obj: bool(obj.get("receptacle"))
            and obj.get("objectType") in {"DiningTable", "CoffeeTable", "SideTable"},
        )
        if table is None:
            table = self._find_first(objects, lambda obj: bool(obj.get("receptacle")))

        key_obj = self._find_first(
            objects, lambda obj: obj.get("objectType") in {"Key", "KeyChain"}
        )
        if key_obj is None:
            key_obj = self._find_first(objects, lambda obj: bool(obj.get("pickupable")))

        if table is not None:
            self._id_aliases[table["objectId"]] = "table_01"
        if key_obj is None:
            return

        self._key_object_id = key_obj["objectId"]
        self._id_aliases[self._key_object_id] = "keys_001"

        if table is not None:
            table_pos = table.get("position", {})
            place_event = self._controller.step(  # type: ignore[union-attr]
                action="PlaceObjectAtPoint",
                objectId=self._key_object_id,
                position={
                    "x": float(table_pos.get("x", 0.0)),
                    "y": float(table_pos.get("y", 0.0)) + 0.9,
                    "z": float(table_pos.get("z", 0.0)),
                },
            )
            if place_event.metadata.get("lastActionSuccess"):
                event = self._controller.step(action="Pass")  # type: ignore[union-attr]
                objects = event.metadata.get("objects", [])
                key_obj = self._find_first(
                    objects, lambda obj: obj.get("objectId") == self._key_object_id
                ) or key_obj

        key_pos = key_obj.get("position", {})
        agent_pos = event.metadata.get("agent", {}).get("position", {})
        target_yaw = self._yaw_to_target(agent_pos, key_pos)
        self._controller.step(  # type: ignore[union-attr]
            action="TeleportFull",
            position={
                "x": float(agent_pos.get("x", 0.0)),
                "y": float(agent_pos.get("y", 0.0)),
                "z": float(agent_pos.get("z", 0.0)),
            },
            rotation={"x": 0.0, "y": target_yaw, "z": 0.0},
            horizon=0.0,
            standing=True,
        )

    def _extract_observation(self, event: Any) -> Observation:
        entities: list[EntityObservation] = []
        metadata = event.metadata

        for obj in metadata.get("objects", []):
            raw_id = str(obj.get("objectId", "unknown_object"))
            entity_id = self._id_aliases.get(raw_id, self._normalize_id(raw_id))
            pos = obj.get("position", {})
            parent = self._extract_parent_receptacle(obj)
            entities.append(
                EntityObservation(
                    entity_id=entity_id,
                    category=self._category_for_object(obj),
                    position=Position(
                        x=float(pos.get("x", 0.0)),
                        y=float(pos.get("y", 0.0)),
                        z=float(pos.get("z", 0.0)),
                    ),
                    visible=bool(obj.get("visible", False)),
                    parent_receptacle=parent,
                    metadata={
                        "object_type": obj.get("objectType"),
                        "distance": obj.get("distance"),
                    },
                )
            )

        agent_meta = metadata.get("agent", {})
        agent_pos = agent_meta.get("position", {})
        entities.append(
            EntityObservation(
                entity_id="agent_001",
                category="Human",
                position=Position(
                    x=float(agent_pos.get("x", 0.0)),
                    y=float(agent_pos.get("y", 0.0)),
                    z=float(agent_pos.get("z", 0.0)),
                ),
                visible=True,
                parent_receptacle=None,
                metadata={"camera_horizon": agent_meta.get("cameraHorizon")},
            )
        )

        entities.append(
            EntityObservation(
                entity_id=self.scene_name.lower(),
                category="Room",
                position=Position(x=0.0, y=0.0, z=0.0),
                visible=True,
                parent_receptacle=None,
                metadata={"scene": self.scene_name},
            )
        )

        return Observation(
            timestamp=self._sim_time,
            frame_id=self._frame_id,
            entities=entities,
        )

    def _extract_parent_receptacle(self, obj: dict[str, Any]) -> str | None:
        parents = obj.get("parentReceptacles") or []
        if not parents:
            return None
        parent = str(parents[0])
        return self._id_aliases.get(parent, self._normalize_id(parent))

    def _category_for_object(self, obj: dict[str, Any]) -> str:
        if bool(obj.get("receptacle")):
            return "Receptacle"
        return "Object"

    def _require_controller(self) -> None:
        if self._controller is None:
            raise RuntimeError("Simulator not initialized. Call initialize() first.")

    @staticmethod
    def _find_first(
        objects: list[dict[str, Any]],
        predicate: Any,
    ) -> dict[str, Any] | None:
        for obj in objects:
            if predicate(obj):
                return obj
        return None

    @staticmethod
    def _yaw_to_target(
        origin: dict[str, Any],
        target: dict[str, Any],
    ) -> float:
        dx = float(target.get("x", 0.0)) - float(origin.get("x", 0.0))
        dz = float(target.get("z", 0.0)) - float(origin.get("z", 0.0))
        angle = math.degrees(math.atan2(dx, dz))
        return (angle + 360.0) % 360.0

    @staticmethod
    def _normalize_id(raw_id: str) -> str:
        cleaned = raw_id.lower()
        for token in ("|", "-", ".", " "):
            cleaned = cleaned.replace(token, "_")
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_")
