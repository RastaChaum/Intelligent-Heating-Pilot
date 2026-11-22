"""Tests for HASchedulerOwnershipResolver: ownership comes from the entity registry."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_ownership_resolver import (
    HASchedulerOwnershipResolver,
)

MODULE = "custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_ownership_resolver"


def _resolver(registry: dict[str, str | None]):
    """Build a resolver over a fake registry mapping entity id to platform (None: no entry)."""
    entity_registry = Mock()
    entity_registry.async_get = lambda entity_id: (
        Mock(platform=registry[entity_id]) if registry.get(entity_id) else None
    )
    patcher = patch(f"{MODULE}.er.async_get", return_value=entity_registry)
    patcher.start()
    name = patch(f"{MODULE}.get_entity_name", side_effect=lambda hass, entity_id: "Friendly")
    name.start()
    resolver = HASchedulerOwnershipResolver(Mock())
    return resolver, (patcher, name)


@pytest.fixture
def stop_patches():
    started: list = []
    yield started
    for patchers in started:
        for patcher in patchers:
            patcher.stop()


@pytest.mark.parametrize(
    ("platform", "kind"),
    [
        ("scheduler", SchedulerKind.HACS),
        ("climate_scheduler", SchedulerKind.CLIMATE_SCHEDULER),
        ("something_else", SchedulerKind.UNKNOWN),
    ],
)
def test_a_switch_is_owned_by_the_integration_that_registered_it(
    platform, kind, stop_patches
) -> None:
    resolver, patchers = _resolver({"switch.plan": platform})
    stop_patches.append(patchers)

    assert resolver.resolve("switch.plan") is kind


def test_a_schedule_helper_is_native_without_a_registry_entry(stop_patches) -> None:
    resolver, patchers = _resolver({})
    stop_patches.append(patchers)

    assert resolver.resolve("schedule.weekdays") is SchedulerKind.NATIVE


def test_a_switch_without_a_registry_entry_is_unknown_and_warns_once(stop_patches, caplog) -> None:
    resolver, patchers = _resolver({})
    stop_patches.append(patchers)

    with caplog.at_level("WARNING", logger=MODULE):
        first = resolver.resolve("switch.plan")
        second = resolver.resolve("switch.plan")

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert first is second is SchedulerKind.UNKNOWN
    assert len(warnings) == 1
    assert "Friendly" in warnings[0].getMessage()
    assert "switch.plan" not in warnings[0].getMessage()


def test_other_domains_are_unknown(stop_patches) -> None:
    resolver, patchers = _resolver({"input_boolean.heating": "input_boolean"})
    stop_patches.append(patchers)

    assert resolver.resolve("input_boolean.heating") is SchedulerKind.UNKNOWN


def test_a_configured_wake_up_source_is_a_timestamp_before_any_registry_lookup() -> None:
    """A phone's alarm sensor belongs to the companion app: only the configuration says what it is."""
    registry = Mock()
    registry.async_get = Mock(return_value=Mock(platform="mobile_app"))
    with patch(f"{MODULE}.er.async_get", return_value=registry):
        resolver = HASchedulerOwnershipResolver(
            Mock(), wake_up_source_ids=frozenset({"sensor.phone_next_alarm"})
        )
        assert resolver.resolve("sensor.phone_next_alarm") is SchedulerKind.TIMESTAMP
        registry.async_get.assert_not_called()


def test_an_entity_that_is_not_a_source_is_resolved_as_before() -> None:
    registry = Mock()
    registry.async_get = Mock(return_value=Mock(platform="scheduler"))
    with patch(f"{MODULE}.er.async_get", return_value=registry):
        resolver = HASchedulerOwnershipResolver(Mock(), wake_up_source_ids=frozenset({"sensor.a"}))
        assert resolver.resolve("switch.plan") is SchedulerKind.HACS
