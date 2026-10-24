"""Value objects for entity attribute mapping and abstraction.

This module provides domain-level abstractions for mapping domain concepts
(like "current temperature") to actual entity attributes, enabling support
for multiple entity types with different attribute structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttributeConcept(Enum):
    """Domain-level concepts that need to be extracted from entities.

    These represent the semantic meaning of data (what we're looking for),
    independent of any specific entity type or Home Assistant attribute name.
    """

    # Climate state attributes
    CURRENT_TEMPERATURE = "current_temperature"
    TARGET_TEMPERATURE = "target_temperature"
    HEATING_ACTIVE = "heating_active"  # Boolean: is heating currently active?

    # For entities that expose hvac_action as a string
    HVAC_ACTION = "hvac_action"

    # Environmental sensor data
    INDOOR_HUMIDITY = "indoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    OUTDOOR_HUMIDITY = "outdoor_humidity"
    CLOUD_COVERAGE = "cloud_coverage"


@dataclass(frozen=True)
class AttributePath:
    """Describes where to find a value in an entity's attributes.

    Supports nested paths like "specific_states.temperature_slope".

    Attributes:
        path: Dot-separated path to the attribute (e.g., "specific_states.temperature")
        fallback_path: Optional fallback path if primary path not found
        required: If True, missing this attribute is an error
    """

    path: str
    fallback_path: str | None = None
    required: bool = True


@dataclass(frozen=True)
class EntityAttributeMapping:
    """Maps domain concepts to actual entity attributes.

    This allows flexible support for different entity types:
    - VTherm with nested "specific_states"
    - Standard Home Assistant climate entities
    - Custom climate entities

    Attributes:
        entity_type: Type of entity (e.g., "climate", "sensor")
        entity_name: Human-readable entity type name (e.g., "VTherm", "Generic Climate")
        mappings: Dict mapping AttributeConcept → list of AttributePath candidates
    """

    entity_type: str
    entity_name: str
    mappings: dict[AttributeConcept, list[AttributePath]]

    def get_attribute_paths(
        self,
        concept: AttributeConcept,
    ) -> list[AttributePath]:
        """Get all possible attribute paths for a concept.

        Returns paths in priority order - first valid path is used.

        Args:
            concept: The domain concept to look up

        Returns:
            List of AttributePath objects (may be empty if concept not supported)
        """
        return self.mappings.get(concept, [])

    def supports_concept(self, concept: AttributeConcept) -> bool:
        """Check if this mapping supports a given concept.

        Args:
            concept: The concept to check

        Returns:
            True if this mapping has at least one path for the concept
        """
        return bool(self.get_attribute_paths(concept))


@dataclass(frozen=True)
class EntityAttributeDescriptor:
    """Describes the attribute structure of an entity instance.

    This is used during setup to identify which entity type we're working with
    and what attributes it actually provides.

    Attributes:
        entity_id: The Home Assistant entity_id (e.g., "climate.living_room")
        entity_type: Type classification (e.g., "climate")
        detected_attributes: Set of attribute names found on this entity
        mapping: The EntityAttributeMapping to use for this entity
    """

    entity_id: str
    entity_type: str
    detected_attributes: set[str]
    mapping: EntityAttributeMapping

    def has_required_attributes(
        self,
        required_concepts: list[AttributeConcept],
    ) -> tuple[bool, list[str]]:
        """Check if entity has attributes needed for required concepts.

        Args:
            required_concepts: List of AttributeConcept needed

        Returns:
            Tuple of (all_present: bool, missing_attributes: list[str])
        """
        missing = []
        for concept in required_concepts:
            paths = self.mapping.get_attribute_paths(concept)
            if not paths:
                # Concept not supported by this mapping
                missing.append(f"{concept.value} (not supported in mapping)")
                continue

            # Check if at least one path exists in detected attributes
            found = False
            for path in paths:
                # Check exact path
                if path.path in self.detected_attributes:
                    found = True
                    break
                # Check fallback path
                if path.fallback_path and path.fallback_path in self.detected_attributes:
                    found = True
                    break

            if not found:
                missing_paths = [p.path for p in paths if not p.fallback_path] + [
                    p.fallback_path for p in paths if p.fallback_path
                ]
                missing.append(
                    f"{concept.value} (expected in {missing_paths}, "
                    f"but only found: {', '.join(self.detected_attributes)})"
                )

        return len(missing) == 0, missing
