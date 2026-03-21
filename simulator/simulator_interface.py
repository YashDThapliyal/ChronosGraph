"""
Abstract interface for world simulators.

Any concrete simulator (grid world, physics engine, multi-agent env, …)
must implement SimulatorInterface so the rest of the system can interact
with it through a stable contract.
"""

from abc import ABC, abstractmethod

from .models import Observation


class SimulatorInterface(ABC):
    """
    Defines the contract every simulator must fulfil.

    Implementations live in simulator/ but must not touch memory logic.
    The ingestion layer calls this interface to pull observations.
    """

    @abstractmethod
    def initialize(self) -> None:
        """
        Prepare the simulator for a new run.

        Called once before any calls to `step()`.  Should allocate
        resources, load maps, seed RNGs, etc.
        """
        ...

    @abstractmethod
    def step(self) -> Observation:
        """
        Advance the simulation by one time step.

        Returns:
            An Observation containing all entity snapshots produced
            during this tick.
        """
        ...

    @abstractmethod
    def get_observation(self) -> Observation:
        """
        Return the most recent observation without advancing the simulator.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset the simulator to its initial state without re-initialising."""
        ...

    @abstractmethod
    def is_done(self) -> bool:
        """
        Indicate whether the simulation episode has ended.

        Returns:
            True if no further steps should be requested.
        """
        ...

    @abstractmethod
    def get_current_time(self) -> float:
        """
        Return the current simulation clock value.

        Returns:
            A monotonically increasing float representing simulation time.
        """
        ...
