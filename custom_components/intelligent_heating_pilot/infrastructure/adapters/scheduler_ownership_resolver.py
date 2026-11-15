"""Home Assistant scheduler ownership resolver.

Implements ISchedulerOwnershipResolver. Climate Scheduler deliberately imitates the HACS
Scheduler attributes, so the look of an entity says nothing about who owns it: the entity
registry does.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ...domain.interfaces.scheduler_ownership_resolver_interface import ISchedulerOwnershipResolver
from ...domain.value_objects.scheduler_kind import SchedulerKind
from .utils import get_entity_name

_LOGGER = logging.getLogger(__name__)

NATIVE_SCHEDULE_DOMAIN_PREFIX = "schedule."
PLATFORM_TO_KIND: dict[str, SchedulerKind] = {
    "scheduler": SchedulerKind.HACS,
    "climate_scheduler": SchedulerKind.CLIMATE_SCHEDULER,
}


class HASchedulerOwnershipResolver(ISchedulerOwnershipResolver):
    """Tells which scheduler integration owns an entity, from the entity registry."""

    def __init__(
        self, hass: HomeAssistant, wake_up_source_ids: frozenset[str] = frozenset()
    ) -> None:
        """Initialize the resolver.

        Args:
            hass: Home Assistant instance.
            wake_up_source_ids: The wake-up sources of this IHP. A source is not a scheduler: a
                phone's alarm sensor belongs to the companion app, which the registry cannot
                tell apart from an unknown scheduler, so the configuration is what says so.
        """
        self._hass = hass
        self._wake_up_source_ids = wake_up_source_ids
        self._warned: set[str] = set()

    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        """Return the kind of scheduler that owns the entity.

        A ``schedule.*`` helper is native by its domain. Any other entity is owned by the
        integration named in its registry entry; without an entry its owner cannot be
        established, which is reported once so the user can see why nothing is actuated.

        Args:
            scheduler_entity_id: Entity id of the scheduler.

        Returns:
            The kind, ``UNKNOWN`` when the owner cannot be established.
        """
        if scheduler_entity_id in self._wake_up_source_ids:
            return SchedulerKind.TIMESTAMP
        if scheduler_entity_id.startswith(NATIVE_SCHEDULE_DOMAIN_PREFIX):
            return SchedulerKind.NATIVE
        entry = er.async_get(self._hass).async_get(scheduler_entity_id)
        if entry is None:
            self._warn_once(scheduler_entity_id)
            return SchedulerKind.UNKNOWN
        return PLATFORM_TO_KIND.get(entry.platform, SchedulerKind.UNKNOWN)

    def _warn_once(self, scheduler_entity_id: str) -> None:
        if scheduler_entity_id in self._warned:
            return
        self._warned.add(scheduler_entity_id)
        _LOGGER.warning(
            "[%s] Scheduler is not in the entity registry, so IHP cannot tell which integration "
            "owns it: the anticipation is computed but nothing is actuated",
            get_entity_name(self._hass, scheduler_entity_id),
        )
