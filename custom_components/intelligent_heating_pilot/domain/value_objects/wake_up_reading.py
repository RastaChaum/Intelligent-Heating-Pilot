"""Wake-up reading value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ReadingIssue(Enum):
    """Why a wake-up source gave no point in time."""

    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    NOT_A_FULL_DATETIME = "not_a_full_datetime"
    UNPARSABLE = "unparsable"


@dataclass(frozen=True)
class WakeUpReading:
    """What a wake-up source held when it was read.

    Attributes:
        value: The point in time, timezone-aware, or None when the source gave none.
        issue: Why there is no value; None when there is one.
    """

    value: datetime | None = None
    issue: ReadingIssue | None = None

    def __post_init__(self) -> None:
        """Validate that a reading is either a value or an issue.

        Raises:
            ValueError: If both or neither are set, or the value has no timezone.
        """
        if (self.value is None) == (self.issue is None):
            raise ValueError("A reading holds either a value or an issue")
        if self.value is not None and self.value.tzinfo is None:
            raise ValueError("A reading value must carry a timezone")
