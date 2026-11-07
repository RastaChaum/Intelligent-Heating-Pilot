"""Regression tests for issue #225: a learning reset racing a cycle recalculation.

Before the fix, a cache refresh that had read the stored cycles before a reset
wrote the old LHS and dead time back right after the reset cleared them. The
reset looked done, yet the old learned values stayed in storage.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    UpdateCacheDataUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import HeatingCycle

DEVICE_ID = "climate.test_vtherm"
CYCLE_START = datetime(2025, 2, 10, 6, 0)
CYCLE_COUNT = 3
DEAD_TIME_GROWTH_MINUTES = 4

# Recorded write order: a learned write after a reset clear is the bug.
LEARNED_WRITES = ("set_global_lhs", "set_contextual_lhs", "set_dead_time")
RESET_CLEARS = ("clear_cycles", "clear_lhs", "clear_dead_time")


def _cycles() -> list[HeatingCycle]:
    """Build cycles whose dead time is learnable."""
    return [
        HeatingCycle(
            device_id=DEVICE_ID,
            start_time=CYCLE_START + timedelta(days=day),
            end_time=CYCLE_START + timedelta(days=day, hours=1),
            target_temp=21.0,
            end_temp=20.5,
            start_temp=18.0,
            tariff_details=None,
            dead_time_cycle_minutes=float(DEAD_TIME_GROWTH_MINUTES * (day + 1)),
        )
        for day in range(CYCLE_COUNT)
    ]


class _Recorder:
    """Shared write log plus a gate that holds the first cycle read."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.cycles_read = asyncio.Event()
        self.release_read = asyncio.Event()

    def recording(self, name: str, result: object = None) -> Callable[..., object]:
        async def _record(*_args: object, **_kwargs: object) -> object:
            self.log.append(name)
            return result

        return _record

    async def gated_cache_read(self, *_args: object) -> Mock:
        """Return the pre-reset cycles, suspended until the test releases it."""
        self.cycles_read.set()
        await self.release_read.wait()
        return Mock(cycles=_cycles())


@pytest.fixture
def recorder() -> _Recorder:
    """Create the shared write log."""
    return _Recorder()


@pytest.fixture
def cycle_storage(recorder: _Recorder) -> Mock:
    """Create a cycle storage whose read is held open by the recorder."""
    storage = Mock()
    storage.prune_old_cycles = AsyncMock(return_value=1)
    storage.get_cache_data = AsyncMock(side_effect=recorder.gated_cache_read)
    storage.append_cycles = AsyncMock()
    storage.clear_cache = AsyncMock(side_effect=recorder.recording("clear_cycles"))
    return storage


@pytest.fixture
def lhs_storage(recorder: _Recorder) -> Mock:
    """Create an LHS storage recording learned writes and reset clears."""
    storage = Mock()
    storage.get_learned_dead_time = AsyncMock(return_value=None)
    storage.clear_slope_history = AsyncMock(side_effect=recorder.recording("clear_lhs"))

    async def set_dead_time(value: float | None) -> None:
        recorder.log.append("clear_dead_time" if value is None else "set_dead_time")

    storage.set_learned_dead_time = AsyncMock(side_effect=set_dead_time)
    return storage


@pytest.fixture
def lhs_manager(recorder: _Recorder) -> Mock:
    """Create an LHS manager recording the global and contextual writes."""
    manager = Mock()
    manager.update_global_lhs_from_cycles = AsyncMock(
        side_effect=recorder.recording("set_global_lhs")
    )
    manager.update_contextual_lhs_from_cycles = AsyncMock(
        side_effect=recorder.recording("set_contextual_lhs")
    )
    manager.invalidate_memory_cache = Mock()
    return manager


@pytest.fixture
def cycle_manager(
    cycle_storage: Mock, lhs_storage: Mock, lhs_manager: Mock
) -> HeatingCycleLifecycleManager:
    """Create a cycle manager learning into the recorded storages."""
    return HeatingCycleLifecycleManager(
        device_config=DeviceConfig(
            device_id=DEVICE_ID,
            vtherm_entity_id=DEVICE_ID,
            scheduler_entities=["schedule.heating"],
            lhs_retention_days=30,
            auto_learning=True,
        ),
        heating_cycle_service=Mock(),
        historical_adapters=[],
        heating_cycle_storage=cycle_storage,
        timer_scheduler=None,
        lhs_storage=lhs_storage,
        lhs_lifecycle_manager=lhs_manager,
    )


@pytest.fixture
def reset_use_case(
    cycle_storage: Mock,
    lhs_storage: Mock,
    lhs_manager: Mock,
    cycle_manager: HeatingCycleLifecycleManager,
) -> UpdateCacheDataUseCase:
    """Create the use case a reset_learning call goes through."""
    return UpdateCacheDataUseCase(cycle_storage, lhs_storage, lhs_manager, cycle_manager)


def _assert_reset_cleared_last(log: list[str]) -> None:
    """Every learned write must come before the reset clears it."""
    assert set(RESET_CLEARS) <= set(log)
    first_clear = min(log.index(name) for name in RESET_CLEARS)
    late_writes = [name for name in log[first_clear:] if name in LEARNED_WRITES]
    assert late_writes == []


async def _reset_while_read_is_held(
    recorder: _Recorder,
    reset_use_case: UpdateCacheDataUseCase,
    recalculation: asyncio.Task,
) -> None:
    """Start a reset while the recalculation waits on its cycle read, then release it."""
    await recorder.cycles_read.wait()
    reset = asyncio.create_task(reset_use_case.reset_cache(DEVICE_ID))
    await asyncio.sleep(0)
    recorder.release_read.set()
    await asyncio.gather(recalculation, reset)


class TestResetDuringRecalculation:
    """A reset must clear what a recalculation started before it learned."""

    @pytest.mark.asyncio
    async def test_reset_during_refresh_after_pruning(
        self,
        recorder: _Recorder,
        cycle_manager: HeatingCycleLifecycleManager,
        reset_use_case: UpdateCacheDataUseCase,
    ) -> None:
        """The refresh that read cycles before the reset does not write after it."""
        cycle_manager._find_missing_date_ranges = AsyncMock(return_value=[])
        refresh = asyncio.create_task(cycle_manager.refresh_heating_cycle_cache())

        await _reset_while_read_is_held(recorder, reset_use_case, refresh)

        assert "set_global_lhs" in recorder.log
        _assert_reset_cleared_last(recorder.log)

    @pytest.mark.asyncio
    async def test_reset_during_extracted_cycles_processing(
        self,
        recorder: _Recorder,
        cycle_manager: HeatingCycleLifecycleManager,
        reset_use_case: UpdateCacheDataUseCase,
    ) -> None:
        """Cycles extracted before the reset do not write learned values after it."""
        processing = asyncio.create_task(cycle_manager._on_cycles_extracted(_cycles()))

        await _reset_while_read_is_held(recorder, reset_use_case, processing)

        assert "set_dead_time" in recorder.log
        _assert_reset_cleared_last(recorder.log)

    @pytest.mark.asyncio
    async def test_reset_waits_while_recalculation_holds_the_lock(
        self,
        recorder: _Recorder,
        cycle_manager: HeatingCycleLifecycleManager,
        reset_use_case: UpdateCacheDataUseCase,
    ) -> None:
        """No storage is cleared until the recalculation in flight has written."""
        cycle_manager._find_missing_date_ranges = AsyncMock(return_value=[])
        refresh = asyncio.create_task(cycle_manager.refresh_heating_cycle_cache())
        await recorder.cycles_read.wait()

        reset = asyncio.create_task(reset_use_case.reset_cache(DEVICE_ID))
        await asyncio.sleep(0)

        assert not any(name in recorder.log for name in RESET_CLEARS)
        recorder.release_read.set()
        await asyncio.gather(refresh, reset)
