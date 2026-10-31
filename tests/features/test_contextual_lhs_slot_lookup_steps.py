"""pytest-bdd step definitions for contextual LHS slot lookup scenarios.

Exercises the real write path (update_contextual_lhs_from_cycles) and read path
(get_contextual_lhs) together, so both sides must agree on the hour key (#183),
including for cycles that reach the target around the slot (#214).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.services.global_lhs_calculator_service import (
    GlobalLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle
from custom_components.intelligent_heating_pilot.domain.value_objects.lhs_cache_entry import (
    LHSCacheEntry,
)

scenarios("contextual_lhs_slot_lookup.feature")
scenarios("contextual_lhs_nearest_hour.feature")

CYCLE_DAY = datetime(2025, 2, 9, tzinfo=UTC)
SLOT_DAY = datetime(2025, 2, 10, tzinfo=UTC)
CYCLE_START_TEMP = 17.0
PREHEAT_SLOPES = (3.0, 4.0)


class InMemoryLhsStorage:
    """Minimal ILhsStorage stand-in that keeps cached LHS values in a dict."""

    def __init__(self) -> None:
        """Start with no cached values."""
        self.global_lhs: LHSCacheEntry | None = None
        self.contextual: dict[int, LHSCacheEntry] = {}

    async def get_cached_global_lhs(self) -> LHSCacheEntry | None:
        """Return the cached global LHS."""
        return self.global_lhs

    async def set_cached_global_lhs(self, value: float, updated_at: datetime) -> None:
        """Cache the global LHS."""
        self.global_lhs = LHSCacheEntry(value=value, updated_at=updated_at)

    async def get_cached_contextual_lhs(self, hour: int) -> LHSCacheEntry | None:
        """Return the cached contextual LHS for an hour."""
        return self.contextual.get(hour)

    async def set_cached_contextual_lhs(
        self, hour: int, value: float, updated_at: datetime
    ) -> None:
        """Cache a contextual LHS for an hour."""
        self.contextual[hour] = LHSCacheEntry(value=value, updated_at=updated_at, hour=hour)

    async def delete_cached_contextual_lhs(self, hour: int) -> None:
        """Forget the contextual LHS of an hour."""
        self.contextual.pop(hour, None)


def _build_manager(storage: InMemoryLhsStorage) -> LhsLifecycleManager:
    return LhsLifecycleManager(
        model_storage=storage,  # type: ignore[arg-type]
        global_lhs_calculator=GlobalLHSCalculatorService(),
        contextual_lhs_calculator=ContextualLHSCalculatorService(),
    )


def _at(day: datetime, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return day.replace(hour=hour, minute=minute)


@pytest.fixture
def slot_context() -> dict:
    """Shared state between steps."""
    return {"cycles": []}


@given("a heating slope learner with persistent storage")
def learner_with_storage(slot_context: dict) -> None:
    """GIVEN: A real lifecycle manager backed by in-memory persistent storage."""
    slot_context["storage"] = InMemoryLhsStorage()
    slot_context["manager"] = _build_manager(slot_context["storage"])


@given(
    parsers.re(
        r"a (?:preheat|daytime|slow) cycle from (?P<start>\d\d:\d\d) to (?P<end>\d\d:\d\d) "
        r"that heated at (?P<slope>[\d.]+) degrees per hour"
    )
)
def heating_cycle(slot_context: dict, start: str, end: str, slope: str) -> None:
    """GIVEN: A recorded heating cycle with a known slope."""
    start_time = _at(CYCLE_DAY, start)
    end_time = _at(CYCLE_DAY, end)
    hours = (end_time - start_time).total_seconds() / 3600
    end_temp = CYCLE_START_TEMP + float(slope) * hours
    slot_context["cycles"].append(
        HeatingCycle(
            device_id="climate.test_vtherm",
            start_time=start_time,
            end_time=end_time,
            target_temp=end_temp,
            end_temp=end_temp,
            start_temp=CYCLE_START_TEMP,
        )
    )


@given(parsers.parse("the global heating slope is {slope:f} degrees per hour"))
def global_slope(slot_context: dict, slope: float) -> None:
    """GIVEN: The room has learned a global heating slope."""
    asyncio.run(slot_context["storage"].set_cached_global_lhs(slope, CYCLE_DAY))


@given(
    parsers.parse(
        "a slope of {slope:f} degrees per hour is stored for {slot} by an earlier version"
    )
)
def stored_slope(slot_context: dict, slope: float, slot: str) -> None:
    """GIVEN: Storage still holds a contextual slope written before the fix (#184)."""
    hour = _at(SLOT_DAY, slot).hour
    asyncio.run(slot_context["storage"].set_cached_contextual_lhs(hour, slope, CYCLE_DAY))


@given(parsers.parse("a slope of {slope:f} degrees per hour was learned earlier for {slot}"))
def earlier_learned_slope(slot_context: dict, slope: float, slot: str) -> None:
    """GIVEN: Storage holds a realistic slope learned from cycles no longer retained."""
    hour = _at(SLOT_DAY, slot).hour
    asyncio.run(slot_context["storage"].set_cached_contextual_lhs(hour, slope, CYCLE_DAY))


@given("the global slope is learned from these cycles")
def learn_global_slope(slot_context: dict) -> None:
    """GIVEN: The write path persists the global slope from the cycles."""
    asyncio.run(slot_context["manager"].update_global_lhs_from_cycles(slot_context["cycles"]))


@given("contextual slopes are learned from these cycles")
def learn_contextual_slopes(slot_context: dict) -> None:
    """GIVEN: The write path persists contextual slopes from the cycles."""
    asyncio.run(slot_context["manager"].update_contextual_lhs_from_cycles(slot_context["cycles"]))


@given("Home Assistant restarts")
def home_assistant_restarts(slot_context: dict) -> None:
    """GIVEN: A fresh manager with empty memory starts up on the same storage."""
    slot_context["manager"] = _build_manager(slot_context["storage"])
    asyncio.run(slot_context["manager"].startup())


@when(parsers.parse("the heating slope for a slot at {slot} is requested"))
def request_slot_slope(slot_context: dict, slot: str) -> None:
    """WHEN: The read path is asked for the slope of a scheduled slot."""
    slot_context["result"] = asyncio.run(
        slot_context["manager"].get_contextual_lhs(
            target_time=_at(SLOT_DAY, slot),
            cycles=slot_context["cycles"],
        )
    )


@then(parsers.parse("the heating slope returned is {expected:f} degrees per hour"))
def slope_returned(slot_context: dict, expected: float) -> None:
    """THEN: The slot uses the slope learned for it."""
    assert slot_context["result"] == pytest.approx(expected, abs=0.01)


@then(parsers.parse("no slope is stored for {slot} any more"))
def no_slope_stored(slot_context: dict, slot: str) -> None:
    """THEN: Storage no longer holds a contextual slope for the slot hour."""
    assert _at(SLOT_DAY, slot).hour not in slot_context["storage"].contextual


@then("the heating slope returned is not learned from the preheat cycles")
def slope_not_from_preheat(slot_context: dict) -> None:
    """THEN: The preheat slopes are not filed under the hour the cycles started."""
    result = slot_context["result"]
    learned = (*PREHEAT_SLOPES, sum(PREHEAT_SLOPES) / len(PREHEAT_SLOPES))
    assert all(result != pytest.approx(value, abs=0.01) for value in learned)
