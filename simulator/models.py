"""
Raw data models produced by the simulator.

These dataclasses represent the lowest-level "sensory" output of the world
simulation: spatial positions and per-entity observation snapshots.  They
are intentionally kept free of any memory or reasoning logic.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    """
    3-D spatial position of an entity in world coordinates.

    Attributes:
        x: Horizontal axis.
        y: Vertical axis (or depth, depending on coordinate convention).
        z: Elevation. Defaults to 0.0 for 2-D environments.
    """

    x: float
    y: float
    z: float = 0.0


@dataclass
class EntityObservation:
    """
    A single observed snapshot of one entity at a specific moment.

    Produced directly by the simulator for each entity visible to the
    observer.  Consumers (e.g. ingestion/) should treat this as raw,
    unvalidated sensor data.

    Attributes:
        entity_id:          Unique identifier of the observed entity.
        category:           One of Object, Human, Receptacle, Room.
        position:           World-space position at the time of observation.
        visible:            Whether the entity is currently visible.
        parent_receptacle:  Parent receptacle id, if known.
        metadata:           Additional raw simulator metadata.
    """

    entity_id: str
    category: str
    position: Position
    visible: bool
    parent_receptacle: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """
    A batch of entity observations produced by the simulator at one tick.

    Each tick the simulator emits one Observation that may contain zero or
    more EntityObservations — one per entity currently perceived by the
    observer.

    Attributes:
        timestamp: Simulation clock time for this observation batch.
        frame_id:  Monotonically increasing frame id.
        entities:  All entity snapshots captured in this tick.
    """

    timestamp: float
    frame_id: int
    entities: list[EntityObservation] = field(default_factory=list)
