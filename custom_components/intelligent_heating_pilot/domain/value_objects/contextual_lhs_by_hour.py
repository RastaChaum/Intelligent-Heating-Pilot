"""Value object for contextual LHS learned for every hour of the day."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

HOURS_PER_DAY = 24


@dataclass(frozen=True)
class ContextualLHSByHour:
    """Contextual LHS learned from a set of cycles, for all 24 hours.

    Rejected hours are kept apart from hours without cycles because they call
    for different handling: a rejected hour must forget any slope stored
    earlier so that it falls back to the global LHS, while an hour without
    cycles keeps what it learned before.

    Attributes:
        learned: Average LHS of the learnable cycles in °C/hour, keyed by hour (0-23).
        rejected_hours: Hours that heated but have no learnable cycle (disturbed, never
            warmed the room, or cached before #255 and slower than the former floor).
    """

    learned: Mapping[int, float] = field(default_factory=dict)
    rejected_hours: frozenset[int] = frozenset()

    def as_hour_map(self) -> dict[int, float | None]:
        """Return the learned LHS for every hour, with None where nothing was learned.

        Returns:
            Mapping {hour: lhs_or_none} covering hours 0-23.
        """
        return {hour: self.learned.get(hour) for hour in range(HOURS_PER_DAY)}
