"""
Observation-to-observation change detector for ChronosGraph Phase 2.
"""

from __future__ import annotations

import math

from config.settings import ChronosGraphSettings
from simulator.models import EntityObservation, Observation

from .event_engine import (
    Event,
    MovedEvent,
    RelationshipChangedEvent,
    VisibilityChangedEvent,
)


class ChangeDetector:
    """Detects movement, visibility, and parent relationship changes."""

    def __init__(self, movement_threshold: float | None = None) -> None:
        settings = ChronosGraphSettings()
        self._movement_threshold = (
            settings.movement_threshold
            if movement_threshold is None
            else movement_threshold
        )

    def detect(self, previous: Observation, current: Observation) -> list[Event]:
        """
        Compare two observations and emit change events.

        Only entities present in both observations are compared.
        """
        prev_by_id = {entity.entity_id: entity for entity in previous.entities}
        curr_by_id = {entity.entity_id: entity for entity in current.entities}

        shared_ids = prev_by_id.keys() & curr_by_id.keys()
        events: list[Event] = []

        for entity_id in sorted(shared_ids):
            prev_entity = prev_by_id[entity_id]
            curr_entity = curr_by_id[entity_id]
            events.extend(
                self._detect_for_entity(
                    previous_entity=prev_entity,
                    current_entity=curr_entity,
                    timestamp=current.timestamp,
                )
            )

        return events

    def _detect_for_entity(
        self,
        previous_entity: EntityObservation,
        current_entity: EntityObservation,
        timestamp: float,
    ) -> list[Event]:
        entity_events: list[Event] = []
        entity_id = current_entity.entity_id

        if previous_entity.position is not None and current_entity.position is not None:
            distance = self._distance(previous_entity, current_entity)
            if distance > self._movement_threshold:
                entity_events.append(
                    MovedEvent(
                        timestamp=timestamp,
                        subject_entity_id=entity_id,
                        old_position=previous_entity.position,
                        new_position=current_entity.position,
                        distance=distance,
                        metadata={},
                    )
                )

        if previous_entity.visible != current_entity.visible:
            entity_events.append(
                VisibilityChangedEvent(
                    timestamp=timestamp,
                    subject_entity_id=entity_id,
                    old_visibility=previous_entity.visible,
                    new_visibility=current_entity.visible,
                    metadata={},
                )
            )

        if previous_entity.parent_receptacle != current_entity.parent_receptacle:
            entity_events.append(
                RelationshipChangedEvent(
                    timestamp=timestamp,
                    subject_entity_id=entity_id,
                    old_parent=previous_entity.parent_receptacle,
                    new_parent=current_entity.parent_receptacle,
                    metadata={},
                )
            )

        return entity_events

    @staticmethod
    def _distance(previous_entity: EntityObservation, current_entity: EntityObservation) -> float:
        prev_pos = previous_entity.position
        curr_pos = current_entity.position
        return math.sqrt(
            (curr_pos.x - prev_pos.x) ** 2
            + (curr_pos.y - prev_pos.y) ** 2
            + (curr_pos.z - prev_pos.z) ** 2
        )
