"""Translation of the stored wake-up source options into domain value objects."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from ...const import (
    CONF_WAKE_UP_ENTITY,
    CONF_WAKE_UP_FROM_SCHEDULE,
    CONF_WAKE_UP_HOLD_MINUTES,
    CONF_WAKE_UP_HORIZON_HOURS,
    CONF_WAKE_UP_PRESET,
    CONF_WAKE_UP_TEMPERATURE,
    DEFAULT_WAKE_UP_HORIZON_HOURS,
)
from ...domain.value_objects.slot_action import SlotAction
from ...domain.value_objects.wake_up_source_config import WakeUpSourceConfig
from ...utils.config_helpers import as_bool

_LOGGER = logging.getLogger(__name__)


def build_wake_up_source(raw: Mapping[str, Any], has_scheduler: bool) -> WakeUpSourceConfig:
    """Build one source from its stored options.

    A "target from the schedule" is only honored with a scheduler on the same IHP; without one
    the fixed target is all there is.

    Args:
        raw: The stored options of the source.
        has_scheduler: Whether the IHP has at least one scheduler.

    Returns:
        The source configuration.

    Raises:
        ValueError: If the options do not make a usable source.
        TypeError: If a value has the wrong type.
    """
    preset = raw.get(CONF_WAKE_UP_PRESET)
    temperature = raw.get(CONF_WAKE_UP_TEMPERATURE)
    fixed = None
    if (isinstance(preset, str) and preset.strip()) or temperature is not None:
        fixed = SlotAction(
            preset=preset.strip() if isinstance(preset, str) and preset.strip() else None,
            temperature=float(temperature) if temperature is not None else None,
        )
    hold_minutes = float(raw.get(CONF_WAKE_UP_HOLD_MINUTES) or 0)
    return WakeUpSourceConfig(
        entity_id=str(raw.get(CONF_WAKE_UP_ENTITY) or ""),
        fixed_target=fixed,
        target_from_schedule=as_bool(raw.get(CONF_WAKE_UP_FROM_SCHEDULE), default=False)
        and has_scheduler,
        horizon=timedelta(
            hours=float(raw.get(CONF_WAKE_UP_HORIZON_HOURS) or DEFAULT_WAKE_UP_HORIZON_HOURS)
        ),
        hold=timedelta(minutes=hold_minutes) if hold_minutes > 0 else None,
    )


def parse_wake_up_sources(raw: Any, has_scheduler: bool) -> tuple[WakeUpSourceConfig, ...]:
    """Parse the stored list of wake-up sources.

    An entry that cannot make a usable source is skipped with a warning, so that one bad entry
    never keeps the integration from loading. An entity listed twice is kept once.

    Args:
        raw: The stored value of the option; anything but a list gives no source.
        has_scheduler: Whether the IHP has at least one scheduler.

    Returns:
        The usable sources, in the stored order.
    """
    if not isinstance(raw, list | tuple):
        return ()
    sources: list[WakeUpSourceConfig] = []
    seen: set[str] = set()
    for entry in raw:
        try:
            source = build_wake_up_source(entry, has_scheduler)
        except (ValueError, TypeError, AttributeError):
            _LOGGER.warning("Ignoring an unusable wake-up source entry: %s", entry)
            continue
        if source.entity_id in seen:
            _LOGGER.warning(
                "Wake-up source %s is listed twice, keeping the first", source.entity_id
            )
            continue
        seen.add(source.entity_id)
        sources.append(source)
    return tuple(sources)
