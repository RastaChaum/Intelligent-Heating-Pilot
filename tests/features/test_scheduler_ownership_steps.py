"""pytest-bdd steps for scheduler ownership: who owns a schedule decides how it is started.

The real routing actuator, the real ownership resolver and the real HACS adapter run against a
mocked ``hass``. Its entity registry gives each switch an owner, and ``scheduler.run_action``
raises, like Home Assistant, when HACS Scheduler is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.actuators import RoutingPreheatActuator
from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HacsRunActionActuator,
    HASchedulerOwnershipResolver,
)

scenarios("scheduler_ownership.feature")

_RESOLVER_MODULE = "custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_ownership_resolver"
_SLOT_TIME = datetime(2025, 2, 10, 7, 0, tzinfo=UTC)


class _ServiceNotFoundError(Exception):
    """Stand-in for Home Assistant's ServiceNotFound (HACS Scheduler absent)."""


@pytest.fixture
def context() -> dict:
    return {"hacs_installed": True, "platform": None, "entity_id": None}


@given(
    parsers.parse('a schedule switch "{entity_id}" owned by "{platform}"'),
)
def switch_owned_by(context: dict, entity_id: str, platform: str) -> None:
    context.update(entity_id=entity_id, platform=platform)


@given(parsers.parse('a schedule switch "{entity_id}" that is not in the entity registry'))
def switch_not_registered(context: dict, entity_id: str) -> None:
    context.update(entity_id=entity_id, platform=None)


@given("HACS Scheduler is not installed")
def hacs_not_installed(context: dict) -> None:
    context["hacs_installed"] = False


@when("the anticipated start is reached")
def anticipated_start_reached(context: dict, caplog: pytest.LogCaptureFixture) -> None:
    hass = Mock()
    hass.services.async_call = AsyncMock(
        side_effect=None
        if context["hacs_installed"]
        else _ServiceNotFoundError("scheduler.run_action")
    )
    registry = Mock()
    registry.async_get = lambda _entity_id: (
        Mock(platform=context["platform"]) if context["platform"] else None
    )
    with (
        patch(f"{_RESOLVER_MODULE}.er.async_get", return_value=registry),
        patch(f"{_RESOLVER_MODULE}.get_entity_name", return_value="Living room plan"),
        caplog.at_level(logging.WARNING),
    ):
        router = RoutingPreheatActuator(
            HASchedulerOwnershipResolver(hass),
            {SchedulerKind.HACS: HacsRunActionActuator(hass)},
        )
        use_case = ControlPreheatingUseCase(router)
        context["proceeded"] = asyncio.run(
            use_case.start_preheating(_SLOT_TIME, 21.0, context["entity_id"])
        )
    context["hass"] = hass
    context["caplog"] = caplog


@then("no scheduler command is sent")
def no_command_sent(context: dict) -> None:
    context["hass"].services.async_call.assert_not_called()


@then("no error is logged")
def no_error_logged(context: dict) -> None:
    errors = [r for r in context["caplog"].records if r.levelno >= logging.ERROR]
    assert errors == []


@then("the preheat is treated as computed only")
def treated_as_computed_only(context: dict) -> None:
    assert context["proceeded"] is True


@then(parsers.parse('the scheduler run action is triggered once for "{entity_id}"'))
def run_action_triggered(context: dict, entity_id: str) -> None:
    context["hass"].services.async_call.assert_called_once()
    assert context["hass"].services.async_call.call_args.args[2]["entity_id"] == entity_id
