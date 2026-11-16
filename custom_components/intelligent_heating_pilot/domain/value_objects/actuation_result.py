"""Actuation result: what an actuator did when asked to start a preheat."""

from __future__ import annotations

from enum import Enum


class ActuationResult(Enum):
    """Outcome of ``IPreheatActuator.start``."""

    ATTEMPTED = "attempted"  # sent; the caller still has to verify the effect (HACS delegation)
    APPLIED = "applied"  # sent and confirmed by the actuator itself
    NOT_APPLIED = "not_applied"  # sent or refused, no effect
    SKIPPED = "skipped"  # a guard stopped it (climate off); nothing was sent
    UNSUPPORTED = "unsupported"  # nothing sent, by design (compute-only scheduler)
