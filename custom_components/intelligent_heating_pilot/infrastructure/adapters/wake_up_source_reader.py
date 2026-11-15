"""Home Assistant wake-up source reader.

Implements IWakeUpSourceReader: it turns the state of a ``sensor`` (device class timestamp), a
``datetime`` or an ``input_datetime`` entity into a reading. It judges nothing: whether the
value is past or too far away is a domain rule.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.interfaces.wake_up_source_reader_interface import IWakeUpSourceReader
from ...domain.value_objects.wake_up_reading import ReadingIssue, WakeUpReading
from .utils import get_entity_name

if TYPE_CHECKING:
    from homeassistant.core import State

_LOGGER = logging.getLogger(__name__)

INPUT_DATETIME_DOMAIN = "input_datetime"
ATTR_HAS_DATE = "has_date"
ATTR_HAS_TIME = "has_time"


class HAWakeUpSourceReader(IWakeUpSourceReader):
    """Reads the point in time held by a source entity."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reader.

        Args:
            hass: Home Assistant instance.
        """
        self._hass = hass
        self._reported: dict[str, tuple[ReadingIssue, str]] = {}

    def read(self, entity_id: str) -> WakeUpReading:
        """Read the point in time held by a source entity.

        Args:
            entity_id: The source entity.

        Returns:
            A reading whose value is timezone-aware, or the reason there is none.
        """
        state = self._hass.states.get(entity_id)
        raw = state.state if state is not None else STATE_UNAVAILABLE
        issue, value = self._interpret(entity_id, state, raw)
        if value is not None:
            self._reported.pop(entity_id, None)
            return WakeUpReading(value=value)
        if issue is None:  # pragma: no cover - an interpretation without value has an issue
            issue = ReadingIssue.UNPARSABLE
        self._report_once(entity_id, issue, raw)
        return WakeUpReading(issue=issue)

    def _interpret(
        self, entity_id: str, state: State | None, raw: str
    ) -> tuple[ReadingIssue | None, datetime | None]:
        """Turn a state into a value or the reason there is none."""
        if state is None or raw == STATE_UNAVAILABLE:
            return ReadingIssue.UNAVAILABLE, None
        if raw in (STATE_UNKNOWN, "", "None"):
            return ReadingIssue.UNKNOWN, None
        if entity_id.startswith(f"{INPUT_DATETIME_DOMAIN}.") and not (
            state.attributes.get(ATTR_HAS_DATE) and state.attributes.get(ATTR_HAS_TIME)
        ):
            return ReadingIssue.NOT_A_FULL_DATETIME, None
        # A date alone parses as that day's midnight: it must be told apart first, since
        # a deadline at an invented midnight would start a preheat for nothing.
        if dt_util.parse_date(raw) is not None or dt_util.parse_time(raw) is not None:
            return ReadingIssue.NOT_A_FULL_DATETIME, None
        parsed = dt_util.parse_datetime(raw)
        if parsed is None:
            return ReadingIssue.UNPARSABLE, None
        return None, parsed if parsed.tzinfo is not None else dt_util.as_local(parsed)

    def _report_once(self, entity_id: str, issue: ReadingIssue, raw: str) -> None:
        """Log an issue once per entity until its state changes."""
        signature = (issue, raw)
        if self._reported.get(entity_id) == signature:
            return
        self._reported[entity_id] = signature
        if issue in (ReadingIssue.UNKNOWN, ReadingIssue.UNAVAILABLE):
            _LOGGER.debug(
                "[%s] Wake-up source gives no time (%s)",
                get_entity_name(self._hass, entity_id),
                issue.value,
            )
            return
        _LOGGER.warning(
            "[%s] Wake-up source ignored: its value %r is %s",
            get_entity_name(self._hass, entity_id),
            raw,
            "not a full date and time"
            if issue is ReadingIssue.NOT_A_FULL_DATETIME
            else "unreadable",
        )
