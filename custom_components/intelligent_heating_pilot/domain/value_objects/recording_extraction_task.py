"""Recording extraction task value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ExtractionTaskState(Enum):
    """States of a recording extraction task."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RecordingExtractionTask:
    """Represents a period extraction task from the Home Assistant Recorder.

    This value object encapsulates all state and metadata for extracting data
    for a specific date range. Tasks are queued and executed sequentially to
    avoid overwhelming the Home Assistant Recorder with concurrent queries.

    The actual extracted cycles are NOT stored in this object; instead they are
    passed to a callback function (on_cycles_extracted) for progressive cache
    population. This keeps the value object lightweight and immutable.

    Attributes:
        start_date: The first day (inclusive) of the extraction period (YYYY-MM-DD).
        end_date: The last day (inclusive) of the extraction period (YYYY-MM-DD).
        device_id: The IHP device identifier for which to extract data.
        state: Current state of the task (PENDING, EXTRACTING, COMPLETED, FAILED).
        error: Error message if extraction failed, None otherwise.
    """

    start_date: date
    end_date: date
    device_id: str
    state: ExtractionTaskState = ExtractionTaskState.PENDING
    error: str | None = None

    def __hash__(self) -> int:
        """Make task hashable based on start_date, end_date, and device_id."""
        return hash((self.start_date, self.end_date, self.device_id))

    def __eq__(self, other: object) -> bool:
        """Compare tasks by start_date, end_date, and device_id."""
        if not isinstance(other, RecordingExtractionTask):
            return False
        return (
            self.start_date == other.start_date
            and self.end_date == other.end_date
            and self.device_id == other.device_id
        )
