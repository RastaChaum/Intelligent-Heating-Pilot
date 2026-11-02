"""Shared rule deciding which heating cycles are learned from, and which learned slopes are used.

The global LHS, the contextual LHS and the dead time all use this rule, so a cycle
rejected by one is never averaged by another (#223, #245).

A cycle is excluded because the thermostat reported a disturbance (load shedding, safety
mode) or because it never warmed the room, not because it heated slowly: a speed floor
cannot tell a disturbed cycle from a genuinely slow heating system such as underfloor
heating, and it dropped the slowest preheats, the very ones that teach IHP to start
earlier (#255).
"""

from __future__ import annotations

from ..constants import LEGACY_MINIMUM_REALISTIC_LHS
from ..value_objects import HeatingCycle


def is_realistic_learning_cycle(cycle: HeatingCycle) -> bool:
    """Tell whether a cycle can be learned from.

    A cycle cached before its disturbance was recorded keeps the former speed floor:
    some of those cycles were disturbed by safety mode (#223), and nothing else tells
    them apart.

    Args:
        cycle: The heating cycle to check.

    Returns:
        True if the cycle was not disturbed, warmed the room and heated after its dead
        time; for a cycle without a learning status, True if its slope is at least
        LEGACY_MINIMUM_REALISTIC_LHS.
    """
    if not cycle.has_learning_status:
        return cycle.avg_heating_slope >= LEGACY_MINIMUM_REALISTIC_LHS
    return (
        cycle.disturbed is False
        and cycle.heating_phase_observed is True
        and cycle.avg_heating_slope > 0
    )


def filter_realistic_cycles(cycles: list[HeatingCycle]) -> list[HeatingCycle]:
    """Keep only the cycles that can be learned from.

    Args:
        cycles: Heating cycles to filter.

    Returns:
        The learnable cycles, in their original order.
    """
    return [cycle for cycle in cycles if is_realistic_learning_cycle(cycle)]


def is_usable_lhs(lhs: float | None) -> bool:
    """Tell whether a learned heating slope can drive an anticipation.

    Any positive slope is usable, however slow: replacing a slow room's slope with the
    default would make its anticipation far too short (#255).

    Args:
        lhs: Learned heating slope in °C/hour, or None if none was learned.

    Returns:
        True if the slope is strictly positive.
    """
    return lhs is not None and lhs > 0
