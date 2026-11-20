"""Regression tests: anticipation must read heating cycles under the device id.

Cycles are stored under the config entry id, but anticipation looked them up
under the VTherm entity id and always got an empty list. Dead time was then
never learned from cycles, and contextual LHS never received any. Fixtures
elsewhere use the same value for both ids, which hid the bug, so these tests
deliberately use different ones.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    CalculateAnticipationUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.services import (
    DeadTimeCalculationService,
    PredictionService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import EnvironmentState
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating_cycle_cache_data import (
    HeatingCycleCacheData,
)

ENTRY_ID = "01JBENTRYID"
VTHERM_ID = "climate.salle"
TARGET_TIME = datetime(2025, 2, 10, 7, 0, 0, tzinfo=UTC)
CYCLE_DEAD_TIMES = (6.0, 10.0)
EXPECTED_DEAD_TIME = 8.0
PERSISTED_DEAD_TIME = 3.0
TARGET_TEMP = 21.0


def _cycle(days_before: int, dead_time: float) -> HeatingCycle:
    """Build a cycle ending at the target hour, some days before the target."""
    end = TARGET_TIME - timedelta(days=days_before)
    return HeatingCycle(
        device_id=ENTRY_ID,
        start_time=end - timedelta(hours=1),
        end_time=end,
        target_temp=TARGET_TEMP,
        end_temp=TARGET_TEMP - 0.5,
        start_temp=18.0,
        dead_time_cycle_minutes=dead_time,
    )


class _KeyedCycleStorage:
    """In-memory cycle storage keyed by device id, like HAHeatingCycleStorage."""

    def __init__(self, cycles: list[HeatingCycle]) -> None:
        self.data = {ENTRY_ID: list(cycles)}

    async def get_cache_data(self, device_id: str) -> HeatingCycleCacheData | None:
        cycles = self.data.get(device_id)
        if cycles is None:
            return None
        return HeatingCycleCacheData(
            device_id=device_id,
            cycles=tuple(cycles),
            last_search_time=TARGET_TIME,
            retention_days=30,
        )

    async def append_cycles(self, device_id: str, cycles: list[HeatingCycle], *_args) -> None:
        self.data.setdefault(device_id, []).extend(cycles)


@pytest.fixture
def cycles() -> list[HeatingCycle]:
    """Cycles stored for the device, with known dead times."""
    return [_cycle(days, dead) for days, dead in enumerate(CYCLE_DEAD_TIMES, start=1)]


@pytest.fixture
def storage(cycles: list[HeatingCycle]) -> _KeyedCycleStorage:
    """Cycle storage holding the cycles under the config entry id only."""
    return _KeyedCycleStorage(cycles)


@pytest.fixture
def cycle_manager(storage: _KeyedCycleStorage) -> HeatingCycleLifecycleManager:
    """Real cycle manager whose device id differs from the VTherm entity id."""
    config = DeviceConfig(
        device_id=ENTRY_ID,
        climate_entity_id=VTHERM_ID,
        scheduler_entities=[],
        lhs_retention_days=30,
    )
    return HeatingCycleLifecycleManager(
        device_config=config,
        heating_cycle_service=Mock(),
        historical_adapters=[],
        heating_cycle_storage=storage,
        timer_scheduler=None,
        lhs_storage=None,
        lhs_lifecycle_manager=None,
    )


@pytest.fixture
def lhs_manager() -> Mock:
    """LHS manager returning fixed slopes."""
    manager = AsyncMock(spec=LhsLifecycleManager)
    manager.get_global_lhs = AsyncMock(return_value=2.0)
    manager.get_contextual_lhs = AsyncMock(return_value=2.0)
    return manager


@pytest.fixture
def lhs_storage() -> Mock:
    """Storage holding a persisted dead time that must not win over the cycles."""
    storage = Mock()
    storage.get_learned_dead_time = AsyncMock(return_value=PERSISTED_DEAD_TIME)
    return storage


@pytest.fixture
def use_case(
    cycle_manager: HeatingCycleLifecycleManager, lhs_manager: Mock, lhs_storage: Mock
) -> CalculateAnticipationUseCase:
    """Anticipation use case wired to the real cycle manager."""
    environment_reader = Mock()
    environment_reader.get_current_environment = AsyncMock(
        return_value=EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            timestamp=TARGET_TIME - timedelta(hours=3),
        )
    )
    climate_reader = Mock()
    climate_reader.get_climate_entity_id = Mock(return_value=VTHERM_ID)
    return CalculateAnticipationUseCase(
        scheduler_reader=None,
        environment_reader=environment_reader,
        climate_data_reader=climate_reader,
        heating_cycle_manager=cycle_manager,
        lhs_lifecycle_manager=lhs_manager,
        prediction_service=PredictionService(),
        dead_time_calculator=DeadTimeCalculationService(),
        auto_learning=True,
        lhs_storage=lhs_storage,
    )


@pytest.mark.asyncio
async def test_dead_time_is_learned_from_cycles_stored_under_device_id(
    use_case: CalculateAnticipationUseCase, lhs_storage: Mock
) -> None:
    """Cycles stored under the entry id give the dead time, not the persisted value."""
    result = await use_case.calculate_anticipation_datas(TARGET_TIME, TARGET_TEMP)

    assert result["dead_time"] == pytest.approx(EXPECTED_DEAD_TIME)
    lhs_storage.get_learned_dead_time.assert_not_awaited()


@pytest.mark.asyncio
async def test_contextual_lhs_receives_cycles_stored_under_device_id(
    use_case: CalculateAnticipationUseCase, lhs_manager: Mock, cycles: list[HeatingCycle]
) -> None:
    """Contextual LHS gets the device cycles instead of an always-empty list."""
    await use_case.calculate_anticipation_datas(TARGET_TIME, TARGET_TEMP)

    passed_cycles = lhs_manager.get_contextual_lhs.await_args.kwargs["cycles"]
    assert passed_cycles == cycles


def test_cycle_manager_exposes_entry_id_as_device_id(
    cycle_manager: HeatingCycleLifecycleManager,
) -> None:
    """The manager reports the id its cycles are stored under."""
    assert cycle_manager.device_id == ENTRY_ID


@pytest.mark.asyncio
async def test_extracted_cycles_are_visible_to_anticipation_the_same_day(
    cycle_manager: HeatingCycleLifecycleManager, cycles: list[HeatingCycle]
) -> None:
    """Cycles extracted after a first read must not be hidden by the memory cache."""
    first = await cycle_manager.get_cycles_for_target_time(ENTRY_ID, TARGET_TIME)
    new_cycle = _cycle(days_before=3, dead_time=20.0)

    await cycle_manager._on_cycles_extracted([new_cycle])
    second = await cycle_manager.get_cycles_for_target_time(ENTRY_ID, TARGET_TIME)

    assert first == cycles
    assert new_cycle in second
