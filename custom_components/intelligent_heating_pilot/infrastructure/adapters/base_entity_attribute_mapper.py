"""Base class for entity attribute mappers.

Provides common functionality for mapping entity attributes to domain concepts.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.entity_attribute_mapper_interface import IEntityAttributeMapper
from ...domain.value_objects.entity_attribute_mapping import (
    AttributeConcept,
    EntityAttributeDescriptor,
    EntityAttributeMapping,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class BaseEntityAttributeMapper(IEntityAttributeMapper):
    """Base implementation for entity attribute mappers.

    Provides common logic for:
    - Navigating nested attribute paths
    - Type conversion
    - Fallback path handling
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the mapper.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass

    @abstractmethod
    def _get_mapping(self) -> EntityAttributeMapping:
        """Get the attribute mapping for this mapper type.

        Must be implemented by subclasses.

        Returns:
            EntityAttributeMapping with entity-specific attribute paths
        """
        pass

    def get_supported_concepts(self) -> list[AttributeConcept]:
        """Get list of domain concepts this mapper can extract.

        Returns:
            List of AttributeConcept values supported by this mapper
        """
        mapping = self._get_mapping()
        return list(mapping.mappings.keys())

    def detect_entity_type(
        self,
        entity_id: str,
    ) -> EntityAttributeDescriptor:
        """Detect and describe an entity's attribute structure.

        This method inspects the entity and determines:
        - What type of entity it is
        - What attributes it actually provides
        - Which mapping should be used for it

        Args:
            entity_id: The Home Assistant entity_id to analyze

        Returns:
            EntityAttributeDescriptor with entity info and appropriate mapping

        Raises:
            ValueError: If entity type cannot be determined or is unsupported
        """
        _LOGGER.debug("Detecting entity type for %s", entity_id)

        # Get current state
        state = self._hass.states.get(entity_id)
        if not state:
            raise ValueError(f"Entity {entity_id} not found in Home Assistant")

        # Collect all attribute names (flat and nested)
        detected_attributes = self._collect_attribute_names(state.attributes)

        _LOGGER.debug(
            "Detected attributes for %s: %s",
            entity_id,
            detected_attributes,
        )

        mapping = self._get_mapping()
        return EntityAttributeDescriptor(
            entity_id=entity_id,
            entity_type=mapping.entity_type,
            detected_attributes=detected_attributes,
            mapping=mapping,
        )

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
            ValueError: If concept not supported by this mapper
        """
        mapping = self._get_mapping()
        paths = mapping.get_attribute_paths(concept)

        if not paths:
            raise ValueError(
                f"Mapper for {mapping.entity_name} does not support concept {concept.value}"
            )

        # Try each possible path in priority order
        for path in paths:
            value = self._get_nested_attribute(attributes, path.path)
            if value is not None:
                _LOGGER.debug(
                    "Extracted %s from path '%s': %s",
                    concept.value,
                    path.path,
                    value,
                )
                return value

            # Try fallback path if available
            if path.fallback_path:
                value = self._get_nested_attribute(attributes, path.fallback_path)
                if value is not None:
                    _LOGGER.debug(
                        "Extracted %s from fallback path '%s': %s",
                        concept.value,
                        path.fallback_path,
                        value,
                    )
                    return value

        # Not found in any path
        _LOGGER.debug(
            "Could not extract %s from attributes (tried paths: %s)",
            concept.value,
            [p.path for p in paths],
        )
        return None

    @staticmethod
    def _get_nested_attribute(
        attributes: dict[str, Any],
        path: str,
    ) -> Any | None:
        """Navigate a dot-separated path through nested attributes.

        Args:
            attributes: Root attributes dict
            path: Dot-separated path (e.g., "specific_states.temperature")

        Returns:
            Value at the path or None if not found
        """
        current: Any = attributes
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return None
            else:
                return None
        return current

    @staticmethod
    def _collect_attribute_names(
        attributes: dict[str, Any],
        prefix: str = "",
    ) -> set[str]:
        """Recursively collect all attribute names (including nested).

        Args:
            attributes: Attributes dict to scan
            prefix: Prefix for nested attributes (used internally)

        Returns:
            Set of all attribute names with dot notation for nested ones
        """
        names = set()
        for key, value in attributes.items():
            full_name = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            names.add(full_name)

            # Recurse into nested dicts (but not too deep to avoid explosion)
            if isinstance(value, dict) and len(prefix.split(".")) < 3:
                names.update(BaseEntityAttributeMapper._collect_attribute_names(value, full_name))

        return names
