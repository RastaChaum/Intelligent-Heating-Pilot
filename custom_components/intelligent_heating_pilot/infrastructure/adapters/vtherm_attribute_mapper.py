"""Attribute mapper for Versatile Thermostat (VTherm) entities.

Handles the complex attribute structure of VTherm with support for
both legacy (pre-v8.0.0) and modern (v8.0.0+) versions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.value_objects.entity_attribute_mapping import (
    AttributeConcept,
    AttributePath,
    EntityAttributeMapping,
)
from .base_entity_attribute_mapper import BaseEntityAttributeMapper

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class VThermAttributeMapper(BaseEntityAttributeMapper):
    """Mapper for Versatile Thermostat (VTherm) entities.

    VTherm (https://github.com/jmcollin78/versatile_thermostat) is a sophisticated
    virtual thermostat integration. Its attributes vary by version:

    - **v8.0.0+**: Uses nested "specific_states" for many attributes
    - **Pre-v8.0.0**: Flat structure with attributes at root level

    This mapper transparently handles both versions.

    See: https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/fr/reference.md#attributs-personnalisés
    """

    def _get_mapping(self) -> EntityAttributeMapping:
        """Get VTherm attribute mapping.

        Maps domain concepts to VTherm's attribute structure with fallbacks
        for different versions.

        Returns:
            EntityAttributeMapping configured for VTherm
        """
        return EntityAttributeMapping(
            entity_type="climate",
            entity_name="VTherm (Versatile Thermostat)",
            mappings={
                # Current temperature as measured by VTherm
                # Tries standard climate attribute first, then VTherm specific ones
                AttributeConcept.CURRENT_TEMPERATURE: [
                    AttributePath(
                        path="current_temperature",
                        fallback_path=None,
                        required=True,
                    ),
                    AttributePath(
                        path="specific_states.current_temperature",
                        fallback_path=None,
                        required=False,
                    ),
                ],
                # Target temperature set by user or automation
                # Standard climate attribute "temperature" is most reliable
                AttributeConcept.TARGET_TEMPERATURE: [
                    AttributePath(
                        path="temperature",
                        fallback_path="target_temperature",
                        required=True,
                    ),
                    AttributePath(
                        path="specific_states.target_temperature",
                        fallback_path=None,
                        required=False,
                    ),
                ],
                # Whether heating is currently active
                # Determined from hvac_action attribute
                # In v8.0.0+, may be in specific_states
                AttributeConcept.HEATING_ACTIVE: [
                    AttributePath(
                        path="hvac_action",
                        fallback_path=None,
                        required=True,
                    ),
                    AttributePath(
                        path="specific_states.hvac_action",
                        fallback_path=None,
                        required=False,
                    ),
                ],
                # Raw hvac_action string (for compatibility)
                AttributeConcept.HVAC_ACTION: [
                    AttributePath(
                        path="hvac_action",
                        fallback_path=None,
                        required=False,
                    ),
                    AttributePath(
                        path="specific_states.hvac_action",
                        fallback_path=None,
                        required=False,
                    ),
                ],
            },
        )
