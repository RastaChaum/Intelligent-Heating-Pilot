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
    PreheatRecovery,
    RecoveryOutcome,
    SchedulerKind,
)
from tests.unit.application.actuators.fakes import make_timeslot


def _actuator(
    result: ActuationResult = ActuationResult.APPLIED,
    outcome: RecoveryOutcome = RecoveryOutcome.NOTHING,
) -> Mock:
    actuator = Mock(spec=IPreheatActuator)
    actuator.start = AsyncMock(return_value=result)
    actuator.cancel = AsyncMock()
    actuator.recover = AsyncMock(
        return_value=PreheatRecovery(
            outcome, make_timeslot() if outcome is RecoveryOutcome.RESUMED else None
        )
    )
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


async def _next_of(_entity_id: str):
    return None


@pytest.mark.asyncio
async def test_recover_asks_every_distinct_actuator_once() -> None:
    hacs, direct = _actuator(), _actuator()
    routes = {
        SchedulerKind.HACS: hacs,
        SchedulerKind.NATIVE: direct,
        SchedulerKind.CLIMATE_SCHEDULER: direct,
    }
    router = _router(SchedulerKind.NATIVE, routes)

    await router.recover(_next_of)

    direct.recover.assert_awaited_once_with(_next_of)
    hacs.recover.assert_awaited_once_with(_next_of)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([RecoveryOutcome.NOTHING, RecoveryOutcome.NOTHING], RecoveryOutcome.NOTHING),
        ([RecoveryOutcome.RELEASED, RecoveryOutcome.NOTHING], RecoveryOutcome.RELEASED),
        ([RecoveryOutcome.RELEASED, RecoveryOutcome.DEFERRED], RecoveryOutcome.DEFERRED),
        ([RecoveryOutcome.DEFERRED, RecoveryOutcome.RESUMED], RecoveryOutcome.RESUMED),
    ],
)
async def test_recover_combines_the_most_telling_outcome(outcomes, expected) -> None:
    first, second = _actuator(outcome=outcomes[0]), _actuator(outcome=outcomes[1])
    router = _router(
        SchedulerKind.NATIVE, {SchedulerKind.HACS: first, SchedulerKind.NATIVE: second}
    )

    assert (await router.recover(_next_of)).outcome is expected


@pytest.mark.asyncio
async def test_a_resumed_recovery_carries_its_slot() -> None:
    router = _router(
        SchedulerKind.NATIVE, {SchedulerKind.NATIVE: _actuator(outcome=RecoveryOutcome.RESUMED)}
    )

    recovery = await router.recover(_next_of)

    assert recovery.timeslot == make_timeslot()


@pytest.mark.asyncio
async def test_a_wake_up_source_slot_goes_to_the_direct_actuator() -> None:
    direct, hacs = _actuator(), _actuator(ActuationResult.ATTEMPTED)
    router = _router(
        SchedulerKind.TIMESTAMP, {SchedulerKind.TIMESTAMP: direct, SchedulerKind.HACS: hacs}
    )

    result = await router.start(make_timeslot(scheduler="sensor.phone_next_alarm"))

    assert result is ActuationResult.APPLIED
    direct.start.assert_awaited_once()
    hacs.start.assert_not_awaited()
