"""Registry for entity attribute mappers.

Manages mapper implementations and provides automatic detection logic
to select the appropriate mapper for a given entity.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.interfaces.entity_attribute_mapper_interface import IEntityAttributeMapper
from .generic_climate_attribute_mapper import GenericClimateAttributeMapper
from .vtherm_attribute_mapper import VThermAttributeMapper

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityAttributeMapperRegistry:
    """Registry for detecting and retrieving entity attribute mappers.

    Automatically detects VTherm, generic climate, and other entity types,
    returning the appropriate mapper for each entity.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the mapper registry.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._mappers: dict[str, IEntityAttributeMapper] = {}
        _LOGGER.debug("Initialized EntityAttributeMapperRegistry")

    def get_mapper_for_entity(
        self,
        entity_id: str,
    ) -> IEntityAttributeMapper:
        """Get or create the appropriate mapper for an entity.

        Auto-detects entity type and returns the correct mapper:
        - VTherm entities → VThermAttributeMapper
        - Generic climate → GenericClimateAttributeMapper
        - Others → raises ValueError

        Caches mappers by entity_id for efficiency.

        Args:
            entity_id: The entity_id to get a mapper for

        Returns:
            IEntityAttributeMapper instance for this entity

        Raises:
            ValueError: If entity type cannot be determined
        """
        # Return cached mapper if available
        if entity_id in self._mappers:
            _LOGGER.debug("Using cached mapper for %s", entity_id)
            return self._mappers[entity_id]

        _LOGGER.debug("Determining mapper for entity %s", entity_id)

        # Try to detect entity type and select appropriate mapper
        mapper = self._select_mapper(entity_id)

        # Cache for future use
        self._mappers[entity_id] = mapper
        _LOGGER.debug("Cached mapper for %s: %s", entity_id, type(mapper).__name__)

        return mapper

    def _select_mapper(
        self,
        entity_id: str,
    ) -> IEntityAttributeMapper:
        """Select the appropriate mapper for an entity.

        Tries mappers in priority order until one succeeds.

        Args:
            entity_id: The entity_id to select a mapper for

        Returns:
            IEntityAttributeMapper instance

        Raises:
            ValueError: If no mapper can handle this entity
        """
        # Get entity state
        state = self._hass.states.get(entity_id)
        if not state:
            raise ValueError(f"Entity {entity_id} not found in Home Assistant")

        # Priority order: VTherm first (most specific), then generic climate
        mappers_to_try = [
            VThermAttributeMapper(self._hass),
            GenericClimateAttributeMapper(self._hass),
        ]

        for mapper in mappers_to_try:
            try:
                # Try to detect entity type with this mapper
                # Note: detect_entity_type is sync in our implementation
                descriptor = mapper.detect_entity_type(entity_id)
                _LOGGER.debug(
                    "Entity %s detected as %s",
                    entity_id,
                    descriptor.mapping.entity_name,
                )

                # Check if mapper has required attributes for basic operation
                from ...domain.value_objects.entity_attribute_mapping import AttributeConcept

                basic_concepts = [
                    AttributeConcept.CURRENT_TEMPERATURE,
                    AttributeConcept.TARGET_TEMPERATURE,
                ]
                has_attrs, missing = descriptor.has_required_attributes(basic_concepts)

                if has_attrs:
                    return mapper

                _LOGGER.debug(
                    "Mapper %s missing attributes: %s",
                    type(mapper).__name__,
                    missing,
                )
            except Exception as err:
                _LOGGER.debug(
                    "Mapper %s cannot handle %s: %s",
                    type(mapper).__name__,
                    entity_id,
                    err,
                )

        # No mapper could handle this entity
        raise ValueError(
            f"No attribute mapper found for entity {entity_id}. "
            f"Supported entity types: VTherm, generic climate. "
            f"Ensure the entity has required attributes (current_temperature, target_temperature, hvac_action)."
        )

    def clear_cache(self) -> None:
        """Clear the mapper cache.

        Useful if entity attributes change and need to be re-detected.
        """
        _LOGGER.debug("Clearing mapper cache")
        self._mappers.clear()
