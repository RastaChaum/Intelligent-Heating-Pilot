"""Regression tests for issue #181: reset_learning must clear in-memory caches.

Before the fix, reset_learning only cleared storage. The lifecycle managers and
HeatingApplication kept serving the old learned values from memory, so the
reset had no visible effect until Home Assistant was restarted.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.application import (
    heating_cycle_lifecycle_manager as lifecycle_module,
)
from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    LearningResetError,
)
from custom_components.intelligent_heating_pilot.const import EVENT_DEAD_TIME_UPDATED
from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_LEARNED_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)

DEVICE_ID = "climate.test_vtherm"
STALE_GLOBAL_LHS = 3.5
STALE_CONTEXTUAL_LHS = 4.2
STALE_DEAD_TIME = 7.0


@pytest.fixture
def empty_model_storage() -> Mock:
    """Create an ILhsStorage mock whose content was just cleared."""
    storage = Mock()
    storage.get_cached_global_lhs = AsyncMock(return_value=None)
    storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
    return storage


@pytest.fixture
def lhs_manager(empty_model_storage: Mock) -> LhsLifecycleManager:
    """Create an LhsLifecycleManager holding stale values in memory."""
    manager = LhsLifecycleManager(
        model_storage=empty_model_storage,
        global_lhs_calculator=Mock(),
        contextual_lhs_calculator=Mock(),
        timer_scheduler=None,
    )
    manager._cached_global_lhs = STALE_GLOBAL_LHS
    manager._cached_contextual_lhs = {6: STALE_CONTEXTUAL_LHS}
    return manager


class TestLhsLifecycleManagerInvalidateMemoryCache:
    """invalidate_memory_cache() must make reads fall through to storage."""

    @pytest.mark.asyncio
    async def test_global_lhs_falls_back_to_default_after_invalidation(
        self, lhs_manager: LhsLifecycleManager, empty_model_storage: Mock
    ) -> None:
        """After invalidation, an empty storage yields the default LHS, not the stale one."""
        lhs_manager.invalidate_memory_cache()

        result = await lhs_manager.get_global_lhs()

        assert result == DEFAULT_LEARNED_SLOPE
        empty_model_storage.get_cached_global_lhs.assert_awaited_once()

    def test_contextual_cache_is_emptied(self, lhs_manager: LhsLifecycleManager) -> None:
        """Contextual LHS values held in memory are dropped."""
        lhs_manager.invalidate_memory_cache()

        assert lhs_manager._cached_global_lhs is None
        assert lhs_manager._cached_contextual_lhs == {}


class TestHeatingCycleLifecycleManagerInvalidateMemoryCache:
    """invalidate_memory_cache() must drop every cached cycle list."""

    def test_cycles_cache_is_emptied(
        self, heating_cycle_manager_minimal: HeatingCycleLifecycleManager
    ) -> None:
        """Cached cycles would otherwise keep feeding dead-time learning."""
        cache_key = (DEVICE_ID, datetime(2025, 2, 10).date())
        heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [Mock()]

        heating_cycle_manager_minimal.invalidate_memory_cache()

        assert heating_cycle_manager_minimal._cached_cycles_for_target_time == {}


class TestHeatingCycleLifecycleManagerCancelExtraction:
    """cancel_extraction() must stop every extraction before the reset clears storage."""

    @pytest.mark.asyncio
    async def test_detached_range_tasks_are_cancelled_and_awaited(
        self, heating_cycle_manager_minimal: HeatingCycleLifecycleManager
    ) -> None:
        """trigger_24h_refresh() detaches its recent-refresh task; it must still be stopped."""
        detached = asyncio.create_task(asyncio.Event().wait())
        heating_cycle_manager_minimal._range_tasks.add(detached)
        detached.add_done_callback(heating_cycle_manager_minimal._range_tasks.discard)
        heating_cycle_manager_minimal._extraction_task = None

        await heating_cycle_manager_minimal.cancel_extraction()

        assert detached.cancelled()
        assert heating_cycle_manager_minimal._range_tasks == set()
        assert heating_cycle_manager_minimal._extraction_queues == []

    @pytest.mark.asyncio
    async def test_queues_are_asked_to_stop(
        self, heating_cycle_manager_minimal: HeatingCycleLifecycleManager
    ) -> None:
        """Queues get the stop request so a queue between two days does not start the next."""
        queue = Mock()
        queue.cancel_queue = AsyncMock()
        heating_cycle_manager_minimal._extraction_queues = [queue]

        await heating_cycle_manager_minimal.cancel_extraction()

        queue.cancel_queue.assert_awaited_once()
        assert heating_cycle_manager_minimal._extraction_queue is None


@pytest.fixture
def app_with_stale_caches() -> HeatingApplication:
    """Create a HeatingApplication whose sensor caches hold stale learned values."""
    device_config = DeviceConfig(
        device_id=DEVICE_ID,
        vtherm_entity_id=DEVICE_ID,
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
    )
    app = HeatingApplication(Mock(), device_config)
    app._orchestrator = Mock()
    app._orchestrator.reset_all_learning_data = AsyncMock()
    app._event_bridge = Mock()
    app._lhs_cache = STALE_GLOBAL_LHS
    app._contextual_lhs_cache = {6: STALE_CONTEXTUAL_LHS}
    return app


class TestHeatingApplicationResetLearning:
    """async_reset_learning() must refresh everything derived from learned data."""

    @pytest.mark.asyncio
    async def test_delegates_reset_to_orchestrator(
        self, app_with_stale_caches: HeatingApplication
    ) -> None:
        """Storage and lifecycle caches are reset through the orchestrator."""
        await app_with_stale_caches.async_reset_learning()

        app_with_stale_caches._orchestrator.reset_all_learning_data.assert_awaited_once_with(
            device_id=DEVICE_ID
        )

    @pytest.mark.asyncio
    async def test_sensor_caches_are_reset(self, app_with_stale_caches: HeatingApplication) -> None:
        """Global LHS goes back to default and previously learned hours become unknown."""
        await app_with_stale_caches.async_reset_learning()

        assert app_with_stale_caches.get_learned_heating_slope() == DEFAULT_LEARNED_SLOPE
        assert app_with_stale_caches.get_contextual_learned_heating_slope(6) is None

    @pytest.mark.asyncio
    async def test_dead_time_event_fired_and_recalculation_requested(
        self, app_with_stale_caches: HeatingApplication
    ) -> None:
        """The Dead Time sensor refreshes and anticipation is recalculated."""
        await app_with_stale_caches.async_reset_learning()

        app_with_stale_caches.hass.bus.async_fire.assert_called_once_with(
            EVENT_DEAD_TIME_UPDATED,
            {"entry_id": DEVICE_ID, "learned_dead_time": None},
        )
        app_with_stale_caches._event_bridge.request_forced_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_caches_refreshed_and_error_raised_when_reset_fails(
        self, app_with_stale_caches: HeatingApplication
    ) -> None:
        """A partial reset still refreshes sensors, which then show what is really stored."""
        app_with_stale_caches._orchestrator.reset_all_learning_data.side_effect = (
            LearningResetError(["learned dead time"])
        )
        app_with_stale_caches._lhs_storage = Mock()
        app_with_stale_caches._lhs_storage.get_learned_dead_time = AsyncMock(
            return_value=STALE_DEAD_TIME
        )

        with pytest.raises(LearningResetError):
            await app_with_stale_caches.async_reset_learning()

        assert app_with_stale_caches._contextual_lhs_cache == {}
        app_with_stale_caches.hass.bus.async_fire.assert_called_once_with(
            EVENT_DEAD_TIME_UPDATED,
            {"entry_id": DEVICE_ID, "learned_dead_time": STALE_DEAD_TIME},
        )
        app_with_stale_caches._event_bridge.request_forced_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_in_flight_finishes_before_reset(
        self, app_with_stale_caches: HeatingApplication
    ) -> None:
        """An update computed before the reset finishes first and stores no dead time (#224)."""
        anticipation_started = asyncio.Event()
        release_anticipation = asyncio.Event()

        async def slow_anticipation(ihp_enabled: bool) -> dict:
            anticipation_started.set()
            await release_anticipation.wait()
            return {"dead_time": STALE_DEAD_TIME + 1}

        app = app_with_stale_caches
        app._orchestrator.calculate_and_schedule_anticipation = slow_anticipation
        app._lhs_storage = Mock()
        app._lhs_storage.set_learned_dead_time = AsyncMock()
        app._lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)
        app._lhs_manager = None

        update = asyncio.create_task(app.async_update())
        await anticipation_started.wait()
        reset = asyncio.create_task(app.async_reset_learning())
        await asyncio.sleep(0)
        app._orchestrator.reset_all_learning_data.assert_not_awaited()

        release_anticipation.set()
        await asyncio.gather(update, reset)

        app._lhs_storage.set_learned_dead_time.assert_not_awaited()
        app._orchestrator.reset_all_learning_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_not_initialized(
        self, app_with_stale_caches: HeatingApplication
    ) -> None:
        """Without an orchestrator, nothing is touched."""
        app_with_stale_caches._orchestrator = None

        await app_with_stale_caches.async_reset_learning()

        assert app_with_stale_caches._lhs_cache == STALE_GLOBAL_LHS
        app_with_stale_caches.hass.bus.async_fire.assert_not_called()


class TestHeatingApplicationRelaunchesExtractionAfterReset:
    """A reset forgets the explored days; extraction must rebuild them right away.

    Before the fix, a device whose startup extraction had already found its cache
    up to date stayed at the default LHS and dead time until the next 24h refresh.
    """

    @pytest.fixture
    def app(self, app_with_stale_caches: HeatingApplication) -> HeatingApplication:
        """Attach a cycle manager to the stale application."""
        app_with_stale_caches._heating_cycle_manager = Mock()
        app_with_stale_caches._heating_cycle_manager.refresh_heating_cycle_cache = AsyncMock()
        return app_with_stale_caches

    @pytest.mark.asyncio
    async def test_extraction_relaunched_after_reset(self, app: HeatingApplication) -> None:
        """The startup extraction window is requested again once the reset is done."""
        await app.async_reset_learning()

        app._heating_cycle_manager.refresh_heating_cycle_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extraction_relaunched_after_partial_reset(self, app: HeatingApplication) -> None:
        """Only unexplored days are extracted, so relearning is safe after a partial reset."""
        app._orchestrator.reset_all_learning_data.side_effect = LearningResetError(["LHS"])
        app._lhs_storage = Mock()
        app._lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)

        with pytest.raises(LearningResetError):
            await app.async_reset_learning()

        app._heating_cycle_manager.refresh_heating_cycle_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extraction_relaunched_outside_learning_lock(
        self, app: HeatingApplication
    ) -> None:
        """Holding the lock would block every anticipation update during the launch."""
        lock_states: list[bool] = []

        async def record_lock_state() -> None:
            lock_states.append(app._learning_lock.locked())

        app._heating_cycle_manager.refresh_heating_cycle_cache.side_effect = record_lock_state

        await app.async_reset_learning()

        assert lock_states == [False]

    @pytest.mark.asyncio
    async def test_not_relaunched_when_extraction_disabled(self, app: HeatingApplication) -> None:
        """A zero history lookback disables extraction, reset included."""
        app._data_retention_days = 0

        await app.async_reset_learning()

        app._heating_cycle_manager.refresh_heating_cycle_cache.assert_not_awaited()


class _BlockingQueue:
    """RecordingExtractionQueue stand-in whose run lasts until ``finish`` is set."""

    instances: list[_BlockingQueue] = []
    finish: asyncio.Event

    def __init__(self, **_kwargs: object) -> None:
        self.populate_queue = AsyncMock(return_value=1)
        self.cancel_queue = AsyncMock()
        _BlockingQueue.instances.append(self)

    async def run_queue(self) -> None:
        await _BlockingQueue.finish.wait()


@pytest.fixture
def blocking_queue() -> Iterator[type[_BlockingQueue]]:
    """Replace the extraction queue so launches can be counted and held open."""
    _BlockingQueue.instances = []
    _BlockingQueue.finish = asyncio.Event()
    with patch.object(lifecycle_module, "RecordingExtractionQueue", _BlockingQueue):
        yield _BlockingQueue
    _BlockingQueue.finish.set()


class TestExtractionNotLaunchedTwice:
    """The reset relaunch and the deferred startup extraction must not both run.

    The startup extraction runs 3 to 11 minutes after Home Assistant starts. If a
    reset already relaunched extraction for the same window, the startup one must
    leave it running instead of cancelling it and redoing the same days.
    """

    @pytest.mark.asyncio
    async def test_second_refresh_keeps_running_extraction(
        self,
        heating_cycle_manager_with_cache: HeatingCycleLifecycleManager,
        blocking_queue: type[_BlockingQueue],
    ) -> None:
        """Reset relaunch, then startup refresh: one extraction, never cancelled."""
        manager = heating_cycle_manager_with_cache

        await manager.refresh_heating_cycle_cache()
        await manager.refresh_heating_cycle_cache()

        assert len(blocking_queue.instances) == 1
        blocking_queue.instances[0].cancel_queue.assert_not_awaited()
        await manager.cancel_extraction()

    @pytest.mark.asyncio
    async def test_concurrent_refreshes_launch_once(
        self,
        heating_cycle_manager_with_cache: HeatingCycleLifecycleManager,
        blocking_queue: type[_BlockingQueue],
    ) -> None:
        """Reset relaunch racing the startup refresh still yields one extraction."""
        manager = heating_cycle_manager_with_cache

        await asyncio.gather(
            manager.refresh_heating_cycle_cache(), manager.refresh_heating_cycle_cache()
        )

        assert len(blocking_queue.instances) == 1
        await manager.cancel_extraction()

    @pytest.mark.asyncio
    async def test_relaunched_after_cancel(
        self,
        heating_cycle_manager_with_cache: HeatingCycleLifecycleManager,
        blocking_queue: type[_BlockingQueue],
    ) -> None:
        """A reset cancels the running extraction; its days must be extracted again."""
        manager = heating_cycle_manager_with_cache
        await manager.refresh_heating_cycle_cache()

        await manager.cancel_extraction()
        await manager.refresh_heating_cycle_cache()

        assert len(blocking_queue.instances) == 2
        await manager.cancel_extraction()

    @pytest.mark.asyncio
    async def test_relaunched_after_extraction_finished(
        self,
        heating_cycle_manager_with_cache: HeatingCycleLifecycleManager,
        blocking_queue: type[_BlockingQueue],
    ) -> None:
        """Days still unexplored after a finished extraction are retried."""
        manager = heating_cycle_manager_with_cache
        await manager.refresh_heating_cycle_cache()
        blocking_queue.finish.set()
        assert manager._extraction_task is not None
        await manager._extraction_task

        await manager.refresh_heating_cycle_cache()

        assert len(blocking_queue.instances) == 2

    @pytest.mark.asyncio
    async def test_new_ranges_still_relaunch(
        self,
        heating_cycle_manager_with_cache: HeatingCycleLifecycleManager,
        blocking_queue: type[_BlockingQueue],
    ) -> None:
        """Ranges outside the running extraction replace it, as before."""
        manager = heating_cycle_manager_with_cache
        await manager._launch_extraction_for_ranges([(date(2025, 2, 3), date(2025, 2, 9))])

        launched = await manager._launch_extraction_for_ranges(
            [(date(2025, 1, 27), date(2025, 2, 9))]
        )

        assert launched is True
        assert len(blocking_queue.instances) == 2
        blocking_queue.instances[0].cancel_queue.assert_awaited_once()
        await manager.cancel_extraction()
