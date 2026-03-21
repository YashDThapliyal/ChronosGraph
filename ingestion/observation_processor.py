"""
Abstract interface for transforming raw simulator observations into
core-ready data.

The ingestion layer is the only module permitted to import from both
`simulator/` and `core/`.  It acts as the translation boundary between
raw world data and the memory system.
"""

from abc import ABC, abstractmethod

from simulator.models import Observation


class ObservationProcessor(ABC):
    """
    Consumes raw `Observation` objects from the simulator and dispatches
    processed data into the core system.

    Concrete implementations will validate data, normalise coordinates,
    enrich entities with metadata, and forward results to
    `EntityManagerInterface` and `EventEngineInterface`.
    """

    @abstractmethod
    def process(self, observation: Observation) -> None:
        """
        Process a single observation batch from the simulator.

        This is the primary entry point.  A concrete implementation should:
        1. Iterate over `observation.entities`.
        2. Retrieve previous state from the entity manager.
        3. Detect changes via the change detector.
        4. Emit resulting events via the event engine.

        Args:
            observation: Raw observation produced by the simulator tick.
        """
        ...

    @abstractmethod
    def flush(self) -> None:
        """
        Flush any internally buffered observations.

        Called when the simulation ends or when a forced flush is needed
        (e.g. end of an episode).
        """
        ...
