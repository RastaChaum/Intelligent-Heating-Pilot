"""Interface for entity attribute mapping and extraction.

This interface defines the contract for translating entity attributes
into domain value objects and concepts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..value_objects.entity_attribute_mapping import (
        AttributeConcept,
        EntityAttributeDescriptor,
    )


class IEntityAttributeMapper(ABC):
    """Contract for mapping entity attributes to domain concepts.

    Implementations handle the complexity of different entity types
    (VTherm with nested structures, generic climate entities, etc.)
    while presenting a unified interface to the domain layer.
    """

    @abstractmethod
    def detect_entity_type(
        self,
        entity_id: str,
    ) -> EntityAttributeDescriptor:
        """Detect and describe an entity's attribute structure.

        This method inspects the entity and determines:
        - What type of entity it is (VTherm, climate, etc.)
        - What attributes it actually provides
        - Which mapping should be used for it

        Args:
            entity_id: The Home Assistant entity_id to analyze

        Returns:
            EntityAttributeDescriptor with entity info and appropriate mapping

        Raises:
            ValueError: If entity type cannot be determined or is unsupported
        """
        pass

    @abstractmethod
    def extract_attribute_value(
        self,
        attributes: dict[str, Any],
        concept: AttributeConcept,
    ) -> Any | None:
        """Extract a value from entity attributes using the concept mapping.

        Tries multiple possible attribute paths (in priority order) to find
        the value, supporting different entity structures transparently.

        Args:
            attributes: The entity's attributes dict
            concept: The domain concept to extract

        Returns:
            The extracted value (could be float, string, bool, etc.) or None if not found

        Raises:
            ValueError: If concept is required but not found
        """
        pass

    @abstractmethod
    def get_supported_concepts(self) -> list[AttributeConcept]:
        """Get list of domain concepts this mapper can extract.

        Returns:
            List of AttributeConcept values supported by this mapper
        """
        pass
