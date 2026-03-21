"""
Abstract interface for persistent belief storage.

Beliefs are higher-level assertions about the world.  The BeliefStore
provides durability so that belief state survives process restarts and
can be audited over time.
"""

from abc import ABC, abstractmethod
from typing import Optional

from core.belief_manager import Belief


class BeliefStoreInterface(ABC):
    """
    Defines the contract for durable belief persistence.

    Implementations should support efficient lookup by belief_id and by
    subject_id so that both direct retrieval and entity-centric queries
    are fast.
    """

    @abstractmethod
    def save_belief(self, belief: Belief) -> None:
        """
        Persist (insert or replace) a belief.

        Args:
            belief: The belief to store.
        """
        ...

    @abstractmethod
    def load_belief(self, belief_id: str) -> Optional[Belief]:
        """
        Load a single belief by its unique ID.

        Args:
            belief_id: Unique identifier of the belief.

        Returns:
            The belief, or None if not found.
        """
        ...

    @abstractmethod
    def load_beliefs_for_subject(
        self,
        subject_id: str,
        predicate: Optional[str] = None,
    ) -> list[Belief]:
        """
        Load all beliefs about a given subject.

        Args:
            subject_id: ID of the entity or concept.
            predicate:  Optional filter by predicate name.

        Returns:
            All matching beliefs ordered by timestamp descending.
        """
        ...

    @abstractmethod
    def delete_belief(self, belief_id: str) -> None:
        """
        Remove a belief from persistent storage.

        Args:
            belief_id: ID of the belief to delete.
        """
        ...

    @abstractmethod
    def list_all_beliefs(self) -> list[Belief]:
        """
        Return all currently stored beliefs.

        Returns:
            A list of all beliefs.
        """
        ...
