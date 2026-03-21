"""
Belief dataclass and abstract belief manager interface.

Beliefs represent the system's current understanding of the world —
higher-level assertions derived from raw observations and event history.
Unlike raw events, beliefs can be retracted or updated as new evidence
arrives.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Belief:
    """
    A single system belief about an entity or world state.

    Beliefs follow a subject–predicate–value (SPV) structure and carry
    a confidence score to support probabilistic reasoning.

    Attributes:
        belief_id:  Unique identifier.  Auto-generated if not provided.
        subject_id: The entity or concept this belief is about.
        predicate:  The property or relation being asserted
                    (e.g. "is_moving", "near", "has_role").
        value:      The asserted value (scalar, string, or nested dict).
        confidence: Certainty in [0.0, 1.0].  Defaults to 1.0.
        timestamp:  Simulation time when this belief was last updated.
        metadata:   Optional provenance or context data.
    """

    belief_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject_id: str = ""
    predicate: str = ""
    value: Any = None
    confidence: float = 1.0
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BeliefManagerInterface(ABC):
    """
    Manages the lifecycle of system beliefs.

    Beliefs are derived from events by higher-level reasoning components
    (Phase 5+).  This interface provides CRUD operations that the rest
    of the system uses to interact with the belief store.
    """

    @abstractmethod
    def assert_belief(self, belief: Belief) -> None:
        """
        Assert or update a belief.

        If a belief with the same `belief_id` already exists it is
        replaced.  If a belief with the same subject/predicate pair
        exists, implementations may choose to merge or replace.

        Args:
            belief: The belief to assert.
        """
        ...

    @abstractmethod
    def retract_belief(self, belief_id: str) -> None:
        """
        Remove a belief from the active belief set.

        Args:
            belief_id: ID of the belief to retract.
        """
        ...

    @abstractmethod
    def query_beliefs(
        self,
        subject_id: str,
        predicate: Optional[str] = None,
    ) -> list[Belief]:
        """
        Return beliefs matching the given criteria.

        Args:
            subject_id: Filter to beliefs about this subject.
            predicate:  Optional further filter by predicate name.

        Returns:
            All matching beliefs, ordered by timestamp descending.
        """
        ...

    @abstractmethod
    def get_belief(self, belief_id: str) -> Optional[Belief]:
        """
        Retrieve a single belief by ID.

        Args:
            belief_id: ID of the belief to retrieve.

        Returns:
            The belief, or None if not found.
        """
        ...
