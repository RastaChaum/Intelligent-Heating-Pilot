"""Unit tests for RoutingPreheatActuator: the scheduler kind picks the actuator."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.actuators.routing_preheat_actuator import (
    RoutingPreheatActuator,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import IPreheatActuator
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    CancelReason,
    SchedulerKind,
)
from tests.unit.application.actuators.fakes import make_timeslot


def _actuator(result: ActuationResult = ActuationResult.APPLIED, recovers: bool = False) -> Mock:
    actuator = Mock(spec=IPreheatActuator)
    actuator.start = AsyncMock(return_value=result)
    actuator.cancel = AsyncMock()
    actuator.recover = AsyncMock(return_value=recovers)
    return actuator


def _router(kind: SchedulerKind, routes: dict[SchedulerKind, Mock]) -> RoutingPreheatActuator:
    resolver = Mock()
    resolver.resolve = Mock(return_value=kind)
    return RoutingPreheatActuator(resolver, routes)


@pytest.mark.asyncio
async def test_a_slot_goes_to_the_actuator_of_its_scheduler_kind() -> None:
    hacs, direct = _actuator(ActuationResult.ATTEMPTED), _actuator()
    router = _router(SchedulerKind.NATIVE, {SchedulerKind.HACS: hacs, SchedulerKind.NATIVE: direct})

    result = await router.start(make_timeslot())

    assert result is ActuationResult.APPLIED
    direct.start.assert_awaited_once()
    hacs.start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [SchedulerKind.UNKNOWN, SchedulerKind.CLIMATE_SCHEDULER])
async def test_a_kind_without_an_actuator_is_unsupported_and_never_raises(kind) -> None:
    router = _router(kind, {SchedulerKind.HACS: _actuator()})

    assert await router.start(make_timeslot()) is ActuationResult.UNSUPPORTED


@pytest.mark.asyncio
async def test_a_cancellation_reaches_the_actuator_of_the_slot() -> None:
    hacs = _actuator()
    router = _router(SchedulerKind.HACS, {SchedulerKind.HACS: hacs})
    slot = make_timeslot()

    await router.cancel(slot, CancelReason.SLOT_CHANGED)

    hacs.cancel.assert_awaited_once_with(slot, CancelReason.SLOT_CHANGED)


@pytest.mark.asyncio
async def test_a_cancellation_for_an_unsupported_kind_does_nothing() -> None:
    router = _router(SchedulerKind.UNKNOWN, {})

    await router.cancel(make_timeslot(), CancelReason.SLOT_CHANGED)  # must not raise


@pytest.mark.asyncio
async def test_recover_asks_every_actuator_once_and_gives_the_slot_to_its_owner() -> None:
    hacs, direct = _actuator(), _actuator(recovers=True)
    routes = {
        SchedulerKind.HACS: hacs,
        SchedulerKind.NATIVE: direct,
        SchedulerKind.CLIMATE_SCHEDULER: direct,
    }
    router = _router(SchedulerKind.NATIVE, routes)
    slot = make_timeslot()

    assert await router.recover(slot) is True
    direct.recover.assert_awaited_once_with(slot)
    hacs.recover.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_recover_without_a_next_slot_asks_everyone_with_none() -> None:
    direct = _actuator()
    router = _router(SchedulerKind.NATIVE, {SchedulerKind.NATIVE: direct})

    assert await router.recover(None) is False
    direct.recover.assert_awaited_once_with(None)
