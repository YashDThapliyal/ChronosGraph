"""Shared world bootstrap orchestration for demo and MCP startup."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

from core.change_detector import ChangeDetector
from core.event_engine import (
    Event,
    EventEngine,
    MovedEvent,
    RelationshipChangedEvent,
    VisibilityChangedEvent,
)
from episodes.complex_episode import ComplexEpisode
from simulator import AI2ThorSimulator
from simulator.models import Observation
from world.world_state_engine import WorldStateEngine

if TYPE_CHECKING:
    from graph.neo4j_graph import Neo4jGraph

DEMO_DELAY_SECONDS = 0.5


def _format_event(event: Event) -> str:
    if isinstance(event, MovedEvent):
        return (
            f"t={event.timestamp:.2f} | MovedEvent | {event.subject_entity_id} "
            f"| distance={event.distance:.2f}"
        )
    if isinstance(event, VisibilityChangedEvent):
        return (
            f"t={event.timestamp:.2f} | VisibilityChangedEvent | "
            f"{event.subject_entity_id} | "
            f"{event.old_visibility}->{event.new_visibility}"
        )
    if isinstance(event, RelationshipChangedEvent):
        old_parent = event.old_parent if event.old_parent is not None else "None"
        new_parent = event.new_parent if event.new_parent is not None else "None"
        return (
            f"t={event.timestamp:.2f} | RelationshipChangedEvent | "
            f"{event.subject_entity_id} | {old_parent}->{new_parent}"
        )
    return f"t={event.timestamp:.2f} | Event | {event.subject_entity_id}"


def _position_dict(pos: Any) -> Optional[dict[str, float]]:
    if pos is None:
        return None
    return {"x": pos.x, "y": pos.y, "z": pos.z}


def bootstrap_world(
    demo: bool = False,
    return_artifacts: bool = False,
    neo4j_graph: Optional["Neo4jGraph"] = None,
) -> WorldStateEngine | tuple[WorldStateEngine, list[dict[str, Any]], list[Any]]:
    """
    Run the hidden-object episode and return a populated world model.

    Args:
        demo:             If True, print frame/event logs and apply a pacing delay.
        return_artifacts: If True, also return event logs grouped by frame and
                          captured frame images from the simulator.
        neo4j_graph:      Optional connected Neo4jGraph instance. When provided,
                          all events and entity snapshots are persisted to Neo4j.
    """
    simulator = AI2ThorSimulator()
    episode = ComplexEpisode()
    change_detector = ChangeDetector()
    event_engine = EventEngine()
    world_engine = WorldStateEngine()
    previous_observation: Observation | None = None
    event_log_text: list[dict[str, Any]] = []
    frames: list[Any] = []

    # Wire in Neo4j stores if a graph connection was provided
    event_store = None
    entity_store = None
    if neo4j_graph is not None:
        from storage.neo4j_event_store import Neo4jEventStore
        from storage.neo4j_entity_store import Neo4jEntityStore
        event_store = Neo4jEventStore(neo4j_graph)
        entity_store = Neo4jEntityStore(neo4j_graph)

    try:
        simulator.initialize()
        episode.initialize(simulator)

        while not episode.is_done():
            current_observation = episode.step(simulator)
            frame_events: list[str] = []

            if demo:
                print(
                    f"\n--- Frame {current_observation.frame_id} "
                    f"| t={current_observation.timestamp:.2f} ---"
                )

            if previous_observation is None:
                world_engine.seed_from_observation(current_observation)

                # Seed Neo4j with the initial state of every entity
                if entity_store is not None:
                    for entity_obs in current_observation.entities:
                        entity_store.save_snapshot(
                            entity_id=entity_obs.entity_id,
                            entity_type=entity_obs.category,
                            state={
                                "parent":   entity_obs.parent_receptacle,
                                "visible":  entity_obs.visible,
                                "position": _position_dict(entity_obs.position),
                            },
                            timestamp=current_observation.timestamp,
                        )
            else:
                changes = change_detector.detect(previous_observation, current_observation)
                event_engine.process_changes(changes)
                for event in changes:
                    world_engine.process_event(event)

                    # Persist to Neo4j
                    if event_store is not None:
                        event_store.save_event(event)
                    if entity_store is not None and isinstance(event, RelationshipChangedEvent):
                        entity = world_engine.entities.get(event.subject_entity_id)
                        entity_store.save_snapshot(
                            entity_id=event.subject_entity_id,
                            entity_type="unknown",
                            state={
                                "parent":   event.new_parent,
                                "visible":  entity.visible if entity else False,
                                "position": _position_dict(
                                    entity.current_position if entity else None
                                ),
                            },
                            timestamp=event.timestamp,
                        )

                    event_text = _format_event(event)
                    frame_events.append(event_text)
                    if demo:
                        print(event_text)

            event_log_text.append(
                {
                    "frame_id":  current_observation.frame_id,
                    "timestamp": current_observation.timestamp,
                    "events":    frame_events,
                }
            )

            controller = simulator._controller
            if controller is not None and getattr(controller, "last_event", None) is not None:
                raw_frame = controller.last_event.frame
                frames.append(raw_frame.copy())
            else:
                frames.append(None)

            previous_observation = current_observation
            if demo:
                time.sleep(DEMO_DELAY_SECONDS)
    finally:
        simulator.shutdown()

    if return_artifacts:
        return world_engine, event_log_text, frames
    return world_engine
