"""Entity validator for initialization checks.

Validates that selected entities have the required attributes before
allowing the integration to start.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.value_objects.entity_attribute_mapping import AttributeConcept
from .entity_attribute_mapper_registry import EntityAttributeMapperRegistry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityAttributeValidator:
    """Validates that entities have required attributes for heating cycle extraction.

    This validator runs during initialization to catch configuration issues early,
    preventing cryptic runtime errors later.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the validator.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._mapper_registry = EntityAttributeMapperRegistry(hass)

    async def validate_entity_compatibility(
        self,
        entity_id: str,
        required_concepts: list[AttributeConcept] | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate that an entity can provide required attributes.

        Checks that:
        1. Entity exists in Home Assistant
        2. Entity type is supported (VTherm, generic climate, etc.)
        3. Entity has attributes needed for the concepts

        Args:
            entity_id: The entity_id to validate
            required_concepts: List of concepts that must be supported.
                             If None, uses default: CURRENT_TEMPERATURE, TARGET_TEMPERATURE, HEATING_ACTIVE

        Returns:
            Tuple of (is_valid: bool, issues: list[str])
            - is_valid: True if entity passes all checks
            - issues: List of problems found (empty if valid)
        """
        issues = []

        # Set default required concepts if not provided
        if required_concepts is None:
            required_concepts = [
                AttributeConcept.CURRENT_TEMPERATURE,
                AttributeConcept.TARGET_TEMPERATURE,
                AttributeConcept.HEATING_ACTIVE,
            ]

        # Check entity exists
        state = self._hass.states.get(entity_id)
        if not state:
            issues.append(f"Entity {entity_id} not found in Home Assistant")
            return False, issues

        # Try to detect entity type and get mapper
        try:
            mapper = self._mapper_registry.get_mapper_for_entity(entity_id)
            _LOGGER.info(
                "Validated entity %s: type=%s",
                entity_id,
                type(mapper).__name__,
            )
        except ValueError as err:
            issues.append(str(err))
            return False, issues

        # Check that entity has required attributes
        try:
            descriptor = mapper.detect_entity_type(entity_id)
        except Exception as err:
            issues.append(f"Cannot analyze entity attributes: {err}")
            return False, issues

        # Validate required concepts
        has_attrs, missing = descriptor.has_required_attributes(required_concepts)
        if not has_attrs:
            issues.extend(missing)
            return False, issues

        # All checks passed
        return True, []

    async def validate_vtherm_for_heating_extraction(
        self,
        entity_id: str,
    ) -> tuple[bool, list[str]]:
        """Validate a VTherm entity for heating cycle extraction.

        Specifically checks that the entity provides the three essential
        measurements needed for LHS calculation:
        - Current indoor temperature
        - Target temperature
        - Whether heating is active

        Args:
            entity_id: The VTherm entity_id to validate

        Returns:
            Tuple of (is_valid: bool, issues: list[str])
        """
        return await self.validate_entity_compatibility(
            entity_id,
            required_concepts=[
                AttributeConcept.CURRENT_TEMPERATURE,
                AttributeConcept.TARGET_TEMPERATURE,
                AttributeConcept.HEATING_ACTIVE,
            ],
        )

    def clear_mapper_cache(self) -> None:
        """Clear the mapper cache after entity config changes.

        Call this if entity attributes change and need to be re-detected.
        """
        self._mapper_registry.clear_cache()
