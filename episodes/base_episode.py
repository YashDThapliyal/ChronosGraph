"""Base episode abstraction for ChronosGraph demos."""

from __future__ import annotations

from abc import ABC, abstractmethod

from simulator import AI2ThorSimulator
from simulator.models import Observation


class Episode(ABC):
    """Abstract episode contract."""

    @abstractmethod
    def initialize(self, simulator: AI2ThorSimulator) -> None:
        """Prepare episode state before stepping."""
        ...

    @abstractmethod
    def step(self, simulator: AI2ThorSimulator) -> Observation:
        """Execute one episode action and return an observation."""
        ...

    @abstractmethod
    def is_done(self) -> bool:
        """Return True when the episode has completed."""
        ...
