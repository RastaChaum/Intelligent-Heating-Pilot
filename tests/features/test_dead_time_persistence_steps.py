"""pytest-bdd step definitions for dead time persistence scenarios (#224).

Runs the real HeatingApplication update and HeatingCycleLifecycleManager cache
refresh against an in-memory learned dead time store, and observes what is
stored as learned and which dead time updates are announced.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.const import EVENT_DEAD_TIME_UPDATED
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle
from custom_components.intelligent_heating_pilot.domain.value_objects.heating_cycle_cache_data import (
    HeatingCycleCacheData,
)
from custom_components.intelligent_heating_pilot.heating_application import HeatingApplication

scenarios("dead_time_persistence.feature")

DEVICE_ID = "entry_living_room"
VTHERM_ID = "climate.living_room"
RETENTION_DAYS = 30
CONFIGURED_DEAD_TIME = 5.0
# Days marked as explored around today, so the refresh finds nothing to extract
EXPLORED_DAYS_MARGIN = 2


class LearnedDeadTimeStore:
    """In-memory learned dead time, recording every write."""

    def __init__(self, value: float | None) -> None:
        self.value = value
        self.writes: list[float | None] = []

    async def get_learned_dead_time(self) -> float | None:
        return self.value

    async def set_learned_dead_time(self, dead_time: float | None) -> None:
        self.value = dead_time
        self.writes.append(dead_time)


@pytest.fixture
def dead_time_context() -> dict[str, Any]:
    """Shared context: the store, the announced dead times and the cached cycles."""
    return {"announced": [], "cycles": []}


def _device_config() -> DeviceConfig:
    return DeviceConfig(
        device_id=DEVICE_ID,
        vtherm_entity_id=VTHERM_ID,
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=RETENTION_DAYS,
        dead_time_minutes=CONFIGURED_DEAD_TIME,
        auto_learning=True,
    )


def _cycle(start: datetime, dead_time_minutes: float) -> HeatingCycle:
    return HeatingCycle(
        device_id=DEVICE_ID,
        start_time=start,
        end_time=start + timedelta(hours=1),
        target_temp=21.0,
        end_temp=20.5,
        start_temp=18.0,
        dead_time_cycle_minutes=dead_time_minutes,
    )


def _new_application(context: dict[str, Any], anticipation_dead_time: float) -> HeatingApplication:
    """Create an application whose anticipation always uses the given dead time."""

    def record_event(event_type: str, event_data: dict[str, Any]) -> None:
        if event_type == EVENT_DEAD_TIME_UPDATED:
            context["announced"].append(event_data["learned_dead_time"])

    hass = Mock()
    hass.bus.async_fire = Mock(side_effect=record_event)
    app = HeatingApplication(hass, _device_config())
    app._orchestrator = Mock()
    app._orchestrator.calculate_and_schedule_anticipation = AsyncMock(
        return_value={"dead_time": anticipation_dead_time}
    )
    app._lhs_storage = context["store"]
    app._lhs_manager = None
    return app


def _cycle_cache(cycles: list[HeatingCycle]) -> Mock:
    """Create a cycle cache holding the cycles, fully explored, with nothing to prune."""
    today = datetime.now(UTC).date()
    explored = frozenset(
        today - timedelta(days=offset)
        for offset in range(-EXPLORED_DAYS_MARGIN, RETENTION_DAYS + EXPLORED_DAYS_MARGIN)
    )
    cache = Mock()
    cache.prune_old_cycles = AsyncMock(return_value=False)
    cache.get_cache_data = AsyncMock(
        return_value=HeatingCycleCacheData(
            device_id=DEVICE_ID,
            cycles=tuple(cycles),
            last_search_time=datetime.now(UTC),
            retention_days=RETENTION_DAYS,
            explored_dates=explored,
        )
    )
    return cache


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given("no learned dead time is stored")
def no_learned_dead_time(dead_time_context: dict[str, Any]) -> None:
    """GIVEN: a new device, or one whose learning was just reset."""
    dead_time_context["store"] = LearnedDeadTimeStore(None)


@given(parsers.parse("a learned dead time of {minutes:g} minutes is stored"))
def learned_dead_time_stored(dead_time_context: dict[str, Any], minutes: float) -> None:
    """GIVEN: a dead time learned in a previous session."""
    dead_time_context["store"] = LearnedDeadTimeStore(minutes)


@given(parsers.parse("cached heating cycles with dead times of {first:g} and {second:g} minutes"))
def cached_cycles(dead_time_context: dict[str, Any], first: float, second: float) -> None:
    """GIVEN: heating cycles already extracted from the history."""
    start = datetime.now(UTC) - timedelta(days=3)
    dead_time_context["cycles"] = [
        _cycle(start, first),
        _cycle(start + timedelta(hours=2), second),
    ]


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when(
    parsers.parse(
        "IHP recalculates the anticipation with the configured dead time of {minutes:g} minutes"
    )
)
def recalculate_with_configured(dead_time_context: dict[str, Any], minutes: float) -> None:
    """WHEN: the anticipation falls back to the configured dead time."""
    app = _new_application(dead_time_context, anticipation_dead_time=minutes)
    asyncio.run(app.async_update())


@when("Home Assistant restarts and IHP recalculates the anticipation twice")
def restart_and_recalculate(dead_time_context: dict[str, Any]) -> None:
    """WHEN: a fresh application runs its updates with the stored dead time."""
    store = dead_time_context["store"]
    app = _new_application(dead_time_context, anticipation_dead_time=store.value)

    async def _run() -> None:
        await app.async_update()
        await app.async_update()

    asyncio.run(_run())


@when("IHP refreshes its heating cycle cache")
def refresh_cycle_cache(dead_time_context: dict[str, Any]) -> None:
    """WHEN: the cache refresh run at startup, after an options change or a reset."""
    manager = HeatingCycleLifecycleManager(
        device_config=_device_config(),
        heating_cycle_service=Mock(),
        historical_adapters=[Mock()],
        heating_cycle_storage=_cycle_cache(dead_time_context["cycles"]),
        timer_scheduler=None,
        lhs_storage=dead_time_context["store"],
        lhs_lifecycle_manager=None,
        dead_time_updated_callback=dead_time_context["announced"].append,
    )
    asyncio.run(manager.refresh_heating_cycle_cache())


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then("nothing is saved as learned dead time")
def nothing_stored(dead_time_context: dict[str, Any]) -> None:
    """THEN: the stored learned dead time is left as it was."""
    assert dead_time_context["store"].writes == []


@then("no dead time update is announced")
def nothing_announced(dead_time_context: dict[str, Any]) -> None:
    """THEN: the Dead Time sensor is not told about an update that did not happen."""
    assert dead_time_context["announced"] == []


@then(parsers.parse("a learned dead time of {minutes:g} minutes is stored"))
def dead_time_stored(dead_time_context: dict[str, Any], minutes: float) -> None:
    """THEN: the average of the cached cycles is stored as learned."""
    assert dead_time_context["store"].writes == [pytest.approx(minutes)]


@then("a dead time update is announced")
def update_announced(dead_time_context: dict[str, Any]) -> None:
    """THEN: the Dead Time sensor refreshes with the learned value."""
    assert dead_time_context["announced"] == [dead_time_context["store"].value]
