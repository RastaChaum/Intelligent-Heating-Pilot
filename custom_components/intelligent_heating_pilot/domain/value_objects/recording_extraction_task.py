"""Recording daily extraction task value object."""

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
    """Represents a single-day extraction task from the Home Assistant Recorder.

    This value object encapsulates all state and metadata for extracting climate
    and environment data for one specific day. Tasks are queued and executed
    sequentially to avoid overwhelming the Home Assistant Recorder with concurrent
    queries.

    The actual extracted cycles are NOT stored in this object; instead they are
    passed to a callback function (on_cycles_extracted) for progressive cache
    population. This keeps the value object lightweight and immutable.

    Attributes:
        extraction_date: The date for which to extract historical data (YYYY-MM-DD).
        device_id: The IHP device identifier for which to extract data.
        climate_entity_id: The VTherm climate entity from which to extract data.
        state: Current state of the task (PENDING, EXTRACTING, COMPLETED, FAILED).
        error: Error message if extraction failed, None otherwise.
    """

    extraction_date: date
    device_id: str
    climate_entity_id: str
    state: ExtractionTaskState = ExtractionTaskState.PENDING
    error: str | None = None

    def __hash__(self) -> int:
        """Make task hashable based on extraction_date and device_id."""
        return hash((self.extraction_date, self.device_id))

    def __eq__(self, other: object) -> bool:
        """Compare tasks by extraction_date and device_id."""
        if not isinstance(other, RecordingExtractionTask):
            return NotImplemented
        return self.extraction_date == other.extraction_date and self.device_id == other.device_id
