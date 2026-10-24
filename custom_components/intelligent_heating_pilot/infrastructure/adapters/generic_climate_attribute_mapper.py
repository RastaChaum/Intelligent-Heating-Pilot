"""Attribute mapper for standard Home Assistant climate entities.

Handles generic climate entities that follow Home Assistant's standard
climate entity attributes (current_temperature, target_temperature, hvac_action).
"""

from __future__ import annotations

import logging

from ...domain.value_objects.entity_attribute_mapping import (
    AttributeConcept,
    AttributePath,
    EntityAttributeMapping,
)
from .base_entity_attribute_mapper import BaseEntityAttributeMapper

_LOGGER = logging.getLogger(__name__)


class GenericClimateAttributeMapper(BaseEntityAttributeMapper):
    """Mapper for generic Home Assistant climate entities.

    Supports standard climate entities that follow the Home Assistant
    climate API conventions:
    - current_temperature: Current measured temperature
    - target_temperature: User-set target temperature
    - hvac_action: Current HVAC action (heating, cooling, idle, etc.)

    This mapper is compatible with most climate integrations that don't
    have their own specialized attribute structures.
    """

    def _get_mapping(self) -> EntityAttributeMapping:
        """Get generic climate attribute mapping.

        Maps domain concepts to standard Home Assistant climate attributes.

        Returns:
            EntityAttributeMapping configured for generic climate entities
        """
        return EntityAttributeMapping(
            entity_type="climate",
            entity_name="Generic Climate Entity",
            mappings={
                # Current temperature as reported by the entity
                AttributeConcept.CURRENT_TEMPERATURE: [
                    AttributePath(
                        path="current_temperature",
                        fallback_path=None,
                        required=True,
                    ),
                ],
                # Target temperature set by the user
                # Standard VTherm uses "temperature", generic climate uses "target_temperature"
                AttributeConcept.TARGET_TEMPERATURE: [
                    AttributePath(
                        path="temperature",
                        fallback_path="target_temperature",
                        required=True,
                    ),
                ],
                # Whether heating is active
                # Determined from hvac_action
                AttributeConcept.HEATING_ACTIVE: [
                    AttributePath(
                        path="hvac_action",
                        fallback_path=None,
                        required=True,
                    ),
                ],
                # Raw hvac_action string
                AttributeConcept.HVAC_ACTION: [
                    AttributePath(
                        path="hvac_action",
                        fallback_path=None,
                        required=False,
                    ),
                ],
            },
        )
