"""Restore decision: what to do with the climate when a preheat ends early."""

from __future__ import annotations

from enum import Enum


class RestoreDecision(Enum):
    """Outcome of ``PreheatSessionPolicy.decide_restore``."""

    RESTORE = "restore"  # the climate is still as IHP left it: put it back
    LEAVE = "leave"  # someone else changed it: write nothing
    DISCARD = "discard"  # the slot is imminent or reached: the scheduler takes over
