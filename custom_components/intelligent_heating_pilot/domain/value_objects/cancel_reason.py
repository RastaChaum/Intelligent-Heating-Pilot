"""Cancel reason: why a preheat is being cancelled."""

from __future__ import annotations

from enum import Enum


class CancelReason(Enum):
    """Why an active preheat is cancelled."""

    SLOT_CHANGED = "slot_changed"
    SCHEDULER_DISABLED = "scheduler_disabled"
    IHP_DISABLED = "ihp_disabled"
    POSTPONED = "postponed"
    SLOT_REACHED = "slot_reached"
