"""Scheduler kind: which integration owns a scheduler entity."""

from __future__ import annotations

from enum import Enum


class SchedulerKind(Enum):
    """The scheduler integrations IHP tells apart."""

    HACS = "hacs"
    NATIVE = "native"
    CLIMATE_SCHEDULER = "climate_scheduler"
    UNKNOWN = "unknown"
