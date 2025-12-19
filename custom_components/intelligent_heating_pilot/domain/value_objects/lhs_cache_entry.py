"""Cached LHS entry value object.

This immutable object carries a cached Learning Heating Slope (LHS) value
along with its last update timestamp and optional contextual hour.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LHSCacheEntry:
    """Represents a cached LHS value and its metadata."""

    value: float
    updated_at: datetime
    hour: int | None = None

    def is_for_hour(self, hour: int) -> bool:
        """Check if the cache entry matches the requested hour."""

        return self.hour == hour