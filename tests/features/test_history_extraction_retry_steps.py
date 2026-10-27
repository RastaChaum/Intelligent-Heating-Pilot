"""pytest-bdd step definitions for history extraction retry scenarios (#187).

Runs the real RecordingExtractionQueue and HeatingCycleService against a fake
history adapter, and observes which periods end up marked as explored.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_bdd import given, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataSet,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    recording_extraction_queue,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.recording_extraction_queue import (
    RecordingExtractionQueue,
)

scenarios("history_extraction_retry.feature")

PERIOD_START = date(2026, 10, 1)
PERIOD_END = date(2026, 10, 7)


@pytest.fixture
def retry_context(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Shared context; the queue's inter-period pause is disabled for speed."""
    monkeypatch.setattr(recording_extraction_queue, "QUEUE_YIELD_SECONDS", 0)
    return {"explored": [], "learned": [], "adapter": Mock()}


@given("a period of 7 days of heating history to extract")
def period_to_extract(retry_context: dict) -> None:
    """GIVEN: a queue for one 7-day period, recording explored periods and learned cycles."""

    async def mark_explored(start: date, end: date) -> None:
        retry_context["explored"].append((start, end))

    async def learn(cycles: list) -> None:
        retry_context["learned"].extend(cycles)

    retry_context["queue"] = RecordingExtractionQueue(
        device_id="entry_id",
        entity_id="climate.living_room",
        historical_adapters=[retry_context["adapter"]],
        heating_cycle_service=HeatingCycleService(),
        on_cycles_extracted=learn,
        on_period_explored=mark_explored,
        task_range_days=7,
    )


@given("the Recorder fails to return the history of that period")
def recorder_fails(retry_context: dict) -> None:
    """GIVEN: the history read fails, as on a Recorder timeout."""
    retry_context["adapter"].fetch_all_historical_data = AsyncMock(
        side_effect=ValueError("Cannot fetch history for entity climate.living_room")
    )


@given("the Recorder has already purged the history of that period")
def recorder_purged(retry_context: dict) -> None:
    """GIVEN: the history read succeeds but returns nothing."""
    retry_context["adapter"].fetch_all_historical_data = AsyncMock(
        return_value=HistoricalDataSet(data={})
    )


@given("Home Assistant shuts down while the history of that period is being read")
def shutdown_during_read(retry_context: dict) -> None:
    """GIVEN: the history read is cancelled."""
    retry_context["adapter"].fetch_all_historical_data = AsyncMock(
        side_effect=asyncio.CancelledError()
    )


@when("IHP extracts the period")
def extract_period(retry_context: dict) -> None:
    """WHEN: the extraction queue runs over the period."""
    queue = retry_context["queue"]

    async def _run() -> None:
        await queue.populate_queue(PERIOD_START, PERIOD_END)
        await queue.run_queue()

    try:
        asyncio.run(_run())
        retry_context["stopped"] = False
    except asyncio.CancelledError:
        retry_context["stopped"] = True


@then("the period is not marked as explored")
def period_not_explored(retry_context: dict) -> None:
    """THEN: the period stays unexplored, so a later refresh reads it again."""
    assert retry_context["explored"] == []


@then("the period is marked as explored")
def period_explored(retry_context: dict) -> None:
    """THEN: the period is never queried again."""
    assert retry_context["explored"] == [(PERIOD_START, PERIOD_END)]


@then("no heating cycles are learned from it")
def no_cycles_learned(retry_context: dict) -> None:
    """THEN: nothing is learned from a history that could not be read."""
    assert retry_context["learned"] == []


@then("the extraction stops")
def extraction_stops(retry_context: dict) -> None:
    """THEN: the cancellation reaches the caller instead of being swallowed."""
    assert retry_context["stopped"] is True
