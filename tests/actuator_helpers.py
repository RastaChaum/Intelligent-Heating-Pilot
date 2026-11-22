"""Shared test helper: a router that actuates HACS Scheduler switches through the real adapter.

Tests that exercise the HACS path with a mocked ``hass`` need ownership without an entity
registry. A switch is taken for a HACS Scheduler one and a ``schedule.*`` helper for a native
one, which has no actuator (compute only), exactly like the production routing table.
"""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.intelligent_heating_pilot.application.actuators import RoutingPreheatActuator
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ISchedulerOwnershipResolver,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HacsRunActionActuator,
)


class PrefixOwnershipResolver(ISchedulerOwnershipResolver):
    """Resolves ownership from the entity id alone."""

    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        if scheduler_entity_id.startswith("schedule."):
            return SchedulerKind.NATIVE
        return SchedulerKind.HACS


def build_hacs_router(hass: Mock) -> RoutingPreheatActuator:
    """Build the production-shaped router over a mocked Home Assistant."""
    return RoutingPreheatActuator(
        PrefixOwnershipResolver(), {SchedulerKind.HACS: HacsRunActionActuator(hass)}
    )
