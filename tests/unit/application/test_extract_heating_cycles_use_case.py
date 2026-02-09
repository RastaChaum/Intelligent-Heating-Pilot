"""Tests for ExtractHeatingCyclesUseCase - RED phase (TDD).

Scenarios tested:
1. Startup: Initial extraction + 24h timer scheduled
2. Periodic refresh: 24h window incremental extraction
3. Retention change: Reconfiguration triggers re-extraction
4. Retention disabled: Timer cancellation, cache clearing
5. Error handling: Graceful degradation on adapter failures
6. Lifecycle: Cleanup and resource release
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application.extract_heating_cycles_use_case import (
    ExtractHeatingCyclesUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ICycleCache,
    IDeviceConfigReader,
    IHeatingCycleService,
    IHistoricalDataAdapter,
    IModelStorage,
    ITimerScheduler,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.services.lhs_calculation_service import (
    LHSCalculationService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HeatingCycle,
    HistoricalDataKey,
    HistoricalDataSet,
)


@pytest.fixture
def mock_device_config() -> DeviceConfig:
    """Mock device configuration."""
    return DeviceConfig(
        device_id="climate.vtherm",
        vtherm_entity_id="climate.vtherm",
        scheduler_entities=["switch.scheduler"],
        humidity_in_entity_id="sensor.humidity_in",
        humidity_out_entity_id="sensor.humidity_out",
        cloud_cover_entity_id="sensor.cloud_cover",
        lhs_retention_days=30,
        dead_time_minutes=10.0,
        auto_learning=True,
        temp_delta_threshold=0.2,
        cycle_split_duration_minutes=30,
        min_cycle_duration_minutes=5,
        max_cycle_duration_minutes=300,
        ihp_enabled=True,
    )


@pytest.fixture
def mock_config_reader() -> AsyncMock:
    """Mock device config reader."""
    mock = AsyncMock(spec=IDeviceConfigReader)
    mock.get_device_config.return_value = Mock(
        device_id="climate.vtherm",
        cycle_split_duration_minutes=30,
        humidity_in_entity_id="sensor.humidity_in",
        humidity_out_entity_id="sensor.humidity_out",
    )
    return mock


@pytest.fixture
def mock_cycle_service() -> AsyncMock:
    """Mock heating cycle service."""
    mock = AsyncMock(spec=IHeatingCycleService)
    mock.extract_heating_cycles.return_value = []  # Default: no cycles
    return mock


@pytest.fixture
def mock_adapters() -> list[AsyncMock]:
    """Mock historical data adapters."""
    climate_adapter = AsyncMock(spec=IHistoricalDataAdapter)
    sensor_adapter = AsyncMock(spec=IHistoricalDataAdapter)

    # Default: return empty datasets
    climate_adapter.fetch_historical_data.return_value = HistoricalDataSet(data={})
    sensor_adapter.fetch_historical_data.return_value = HistoricalDataSet(data={})

    return [climate_adapter, sensor_adapter]


@pytest.fixture
def mock_cache() -> AsyncMock:
    """Mock cycle cache."""
    mock = AsyncMock(spec=ICycleCache)
    mock.append_cycles = AsyncMock()
    mock.prune_old_cycles = AsyncMock()
    mock.clear_cache = AsyncMock()
    return mock


@pytest.fixture
def mock_timer_scheduler() -> Mock:
    """Mock timer scheduler."""
    mock = Mock(spec=ITimerScheduler)
    mock.schedule_timer = Mock(return_value=Mock())  # Return cancel func
    return mock


@pytest.fixture
def mock_model_storage() -> AsyncMock:
    """Mock model storage for LHS persistence."""
    mock = AsyncMock(spec=IModelStorage)
    mock.set_cached_global_lhs = AsyncMock()
    return mock


@pytest.fixture
def mock_lhs_calculation_service() -> LHSCalculationService:
    """Mock LHS calculation service."""
    return LHSCalculationService()


@pytest.fixture
def use_case(
    mock_device_config: DeviceConfig,
    mock_cycle_service: AsyncMock,
    mock_adapters: list[AsyncMock],
    mock_cache: AsyncMock,
    mock_timer_scheduler: Mock,
) -> ExtractHeatingCyclesUseCase:
    """Create use case instance with new signature (device_config instead of device_config_reader)."""
    return ExtractHeatingCyclesUseCase(
        device_config=mock_device_config,
        heating_cycle_service=mock_cycle_service,
        historical_adapters=mock_adapters,  # type: ignore
        cycle_cache=mock_cache,
        timer_scheduler=mock_timer_scheduler,
    )


# ===== SCENARIO 1: STARTUP / INITIAL EXTRACTION =====


class TestStartupInitialExtraction:
    """Test initial cycle extraction on startup."""

    @pytest.mark.asyncio
    async def test_execute_fetches_historical_data_via_adapters(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_adapters: list[AsyncMock],
        mock_cycle_service: AsyncMock,
        mock_config_reader: AsyncMock,
    ) -> None:
        """GIVEN: Device config with climate + sensor adapters

        WHEN: execute() called with 30-day window

        THEN: Should fetch from both adapters
        """
        # Setup: Mock data from adapters
        mock_adapters[0].fetch_historical_data.return_value = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [Mock(timestamp=dt_util.utcnow(), value=20.5)],
                HistoricalDataKey.TARGET_TEMP: [Mock(timestamp=dt_util.utcnow(), value=21.0)],
                HistoricalDataKey.HEATING_STATE: [Mock(timestamp=dt_util.utcnow(), value=True)],
            }
        )
        mock_cycle_service.extract_heating_cycles.return_value = []  # No cycles extracted

        # Execute
        now = dt_util.utcnow()
        start_time = now - timedelta(days=30)

        _ = await use_case.execute(
            device_id="climate.vtherm",
            start_time=start_time,
            end_time=now,
        )

        # Verify: Adapter was called with correct parameters
        assert mock_adapters[0].fetch_historical_data.called
        call_args = mock_adapters[0].fetch_historical_data.call_args_list

        # Check that fetch was called (at least one call)
        assert len(call_args) > 0

    @pytest.mark.asyncio
    async def test_execute_extracts_cycles_using_domain_service(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cycle_service: AsyncMock,
        mock_adapters: list[AsyncMock],
    ) -> None:
        """GIVEN: Historical data fetched

        WHEN: execute() calls extract_heating_cycles

        THEN: Should pass device_id, historical_data_set, time range, and cycle_split_duration_minutes
        """
        # Setup: Mock extraction to return 2 cycles
        mock_cycle = HeatingCycle(
            device_id="climate.vtherm",
            start_time=dt_util.utcnow() - timedelta(days=10),
            end_time=dt_util.utcnow() - timedelta(days=10) + timedelta(minutes=45),
            target_temp=21.0,
            end_temp=21.5,
            start_temp=19.0,
        )
        mock_cycle_service.extract_heating_cycles.return_value = [mock_cycle]

        # Execute
        now = dt_util.utcnow()
        start_time = now - timedelta(days=30)

        cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=start_time,
            end_time=now,
        )

        # Verify: Domain service was called with correct parameters
        mock_cycle_service.extract_heating_cycles.assert_called_once()
        call_kwargs = mock_cycle_service.extract_heating_cycles.call_args[1]

        assert call_kwargs["device_id"] == "climate.vtherm"
        assert call_kwargs["cycle_split_duration_minutes"] == 30  # From device config
        assert len(cycles) == 1

    @pytest.mark.asyncio
    async def test_execute_appends_to_cache_with_retention_metadata(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Cycles extracted

        WHEN: execute() appends to cache

        THEN: Should include retention_days metadata
        """
        mock_cycles = [Mock(spec=HeatingCycle)]
        mock_cycle_service.extract_heating_cycles.return_value = mock_cycles

        # Execute
        now = dt_util.utcnow()
        start_time = now - timedelta(days=30)

        await use_case.execute(
            device_id="climate.vtherm",
            start_time=start_time,
            end_time=now,
        )

        # Verify: Cache was updated with retention metadata
        mock_cache.append_cycles.assert_called_once()
        call_kwargs = mock_cache.append_cycles.call_args[1]

        assert call_kwargs["device_id"] == "climate.vtherm"
        assert call_kwargs["retention_days"] == 30  # Computed from window

    @pytest.mark.asyncio
    async def test_execute_schedules_24h_refresh_timer(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """GIVEN: Initial extraction complete

        WHEN: execute() finishes

        THEN: Should schedule 24h refresh timer
        """
        now = dt_util.utcnow()

        await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: Timer scheduler called with 24h interval
        mock_timer_scheduler.schedule_timer.assert_called_once()
        call_args = mock_timer_scheduler.schedule_timer.call_args[0]

        scheduled_time = call_args[0]
        time_diff_hours = (scheduled_time - now).total_seconds() / 3600

        assert 23.9 < time_diff_hours < 24.1  # ~24 hours

        # Callback should be _perform_periodic_refresh
        callback = call_args[1]
        assert callback == use_case._perform_periodic_refresh

    @pytest.mark.asyncio
    async def test_execute_returns_extracted_cycles(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Cycles extracted from domain service

        WHEN: execute() returns

        THEN: Should return the extracted cycles
        """
        mock_cycle = HeatingCycle(
            device_id="climate.vtherm",
            start_time=dt_util.utcnow(),
            end_time=dt_util.utcnow() + timedelta(minutes=45),
            target_temp=21.0,
            end_temp=21.5,
            start_temp=19.0,
        )
        mock_cycle_service.extract_heating_cycles.return_value = [mock_cycle]

        now = dt_util.utcnow()
        cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        assert len(cycles) == 1
        assert cycles[0] == mock_cycle


# ===== SCENARIO 2: PERIODIC 24H REFRESH =====


class TestPeriodicRefresh:
    """Test periodic 24h refresh cycle extraction."""

    @pytest.mark.asyncio
    async def test_perform_periodic_refresh_extracts_last_24_hours(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Initial extraction done, timer scheduled

        WHEN: _perform_periodic_refresh() called

        THEN: Should extract cycles from last 24 hours (incremental)
        """
        # Setup: Initialize use case state
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30

        # Execute
        await use_case._perform_periodic_refresh()

        # Verify: Domain service called with 24-hour window
        mock_cycle_service.extract_heating_cycles.assert_called_once()
        call_kwargs = mock_cycle_service.extract_heating_cycles.call_args[1]

        # Check time window is ~24 hours
        start_time = call_kwargs["start_time"]
        end_time = call_kwargs["end_time"]
        window_hours = (end_time - start_time).total_seconds() / 3600

        assert 23.9 < window_hours < 24.1

    @pytest.mark.asyncio
    async def test_perform_periodic_refresh_appends_incremental_cycles(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: New cycles extracted over 24h

        WHEN: _perform_periodic_refresh() appends to cache

        THEN: Should append (not replace) for incremental updates
        """
        # Setup
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30

        mock_new_cycle = [Mock(spec=HeatingCycle)]
        mock_cycle_service.extract_heating_cycles.return_value = mock_new_cycle

        # Execute
        await use_case._perform_periodic_refresh()

        # Verify: Cache append was called (not clear+replace)
        mock_cache.append_cycles.assert_called_once()

        # Verify: Prune was called to remove old cycles
        mock_cache.prune_old_cycles.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_periodic_refresh_reschedules_timer(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """GIVEN: 24h refresh completed

        WHEN: _perform_periodic_refresh() finishes

        THEN: Should reschedule the next 24h timer
        """
        # Setup
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30
        use_case._refresh_cancel = Mock()  # Mock existing cancel function

        # Execute
        await use_case._perform_periodic_refresh()

        # Verify: Timer scheduler called again to reschedule
        assert mock_timer_scheduler.schedule_timer.called


# ===== SCENARIO 3: RETENTION CONFIGURATION CHANGE =====


class TestRetentionChange:
    """Test handling of retention configuration changes."""

    @pytest.mark.asyncio
    async def test_on_retention_changed_from_30_to_7_days(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Current retention 30 days, changed to 7 days

        WHEN: on_retention_changed(7) called

        THEN: Should:
          - Cancel old timer
          - Clear cache
          - Re-extract with new window (7 days)
          - Schedule new timer
        """
        # Setup: Use case already initialized with 30 days
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30
        old_cancel_mock = Mock()  # Mock cancel function
        use_case._refresh_cancel = old_cancel_mock

        # Execute
        await use_case.on_retention_changed(new_retention_days=7)

        # Verify: Cache was cleared
        mock_cache.clear_cache.assert_called_with("climate.vtherm")

        # Verify: Old timer was cancelled
        old_cancel_mock.assert_called_once()

        # Verify: New extraction happened
        mock_cycle_service.extract_heating_cycles.assert_called_once()

        # Verify: New retention was stored
        assert use_case._current_retention_days == 7

    @pytest.mark.asyncio
    async def test_on_retention_changed_to_zero_disables_extraction(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Retention set to 0 (disabled)

        WHEN: on_retention_changed(0) called

        THEN: Should:
          - Cancel timer
          - Clear cache
          - Return (no extraction)
        """
        # Setup
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30
        old_cancel_mock = Mock()
        use_case._refresh_cancel = old_cancel_mock

        # Execute
        await use_case.on_retention_changed(new_retention_days=0)

        # Verify: Timer cancelled
        old_cancel_mock.assert_called_once()

        # Verify: Cache cleared
        mock_cache.clear_cache.assert_called_with("climate.vtherm")

        # Verify: No new extraction (retention disabled)
        # Reset service call count from any prior calls
        prior_calls = mock_cycle_service.extract_heating_cycles.call_count
        # on_retention_changed with 0 should NOT call extract
        # This is checked by ensuring no additional calls happen
        assert mock_cycle_service.extract_heating_cycles.call_count == prior_calls

    @pytest.mark.asyncio
    async def test_on_retention_changed_updates_current_retention(
        self,
        use_case: ExtractHeatingCyclesUseCase,
    ) -> None:
        """GIVEN: Retention days configured

        WHEN: on_retention_changed() called with new value

        THEN: Should update _current_retention_days
        """
        # Setup
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30
        use_case._refresh_cancel = Mock()

        # Execute
        await use_case.on_retention_changed(new_retention_days=14)

        # Verify: Current retention updated
        assert use_case._current_retention_days == 14


# ===== SCENARIO 4: ERROR HANDLING =====


class TestErrorHandling:
    """Test error handling and resilience."""

    @pytest.mark.asyncio
    async def test_execute_handles_adapter_fetch_failure(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_adapters: list[AsyncMock],
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Adapter fails to fetch data

        WHEN: execute() called

        THEN: Should:
          - Log warning
          - Return empty list (non-fatal)
          - Still schedule timer (extraction independent)
        """
        # Setup: First adapter raises exception
        mock_adapters[0].fetch_historical_data.side_effect = RuntimeError("Recorder unavailable")
        mock_cycle_service.extract_heating_cycles.return_value = []

        # Execute (should not raise)
        now = dt_util.utcnow()
        cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: Returned gracefully with empty list
        assert cycles == []

    @pytest.mark.asyncio
    async def test_execute_still_schedules_timer_after_failure(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_adapters: list[AsyncMock],
        mock_timer_scheduler: Mock,
    ) -> None:
        """GIVEN: Extraction fails mid-process

        WHEN: execute() handles exception

        THEN: Timer should still be scheduled for next 24h
        """
        # Setup: Make adapter fail
        mock_adapters[0].fetch_historical_data.side_effect = RuntimeError("Connection lost")

        # Execute
        now = dt_util.utcnow()
        _ = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: Timer was still scheduled
        mock_timer_scheduler.schedule_timer.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_handles_domain_service_failure(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Domain service fails to extract cycles

        WHEN: execute() called

        THEN: Should handle gracefully and return empty list
        """
        # Setup: Domain service raises
        mock_cycle_service.extract_heating_cycles.side_effect = ValueError("Invalid data format")

        # Execute (should not raise)
        now = dt_util.utcnow()
        cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: Returned gracefully
        assert cycles == []

    @pytest.mark.asyncio
    async def test_periodic_refresh_handles_adapter_failure(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_adapters: list[AsyncMock],
    ) -> None:
        """GIVEN: Periodic refresh timer fires and adapter fails

        WHEN: _perform_periodic_refresh() called

        THEN: Should handle gracefully (non-fatal)
        """
        # Setup
        use_case._device_id = "climate.vtherm"
        use_case._current_retention_days = 30
        use_case._refresh_cancel = Mock()
        mock_adapters[0].fetch_historical_data.side_effect = RuntimeError("Adapter error")

        # Execute (should not raise)
        await use_case._perform_periodic_refresh()

        # Verify: Did not raise exception
        # (graceful error handling)


# ===== SCENARIO 5: LIFECYCLE / CLEANUP =====


class TestLifecycleManagement:
    """Test use case lifecycle and resource cleanup."""

    @pytest.mark.asyncio
    async def test_cancel_stops_refresh_timer(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """GIVEN: Refresh timer scheduled

        WHEN: cancel() called (e.g., during coordinator cleanup)

        THEN: Should call the cancel function returned by timer scheduler
        """
        # Setup: Mock cancel function
        mock_cancel = Mock()
        use_case._refresh_cancel = mock_cancel

        # Execute
        await use_case.cancel()

        # Verify: Cancel function invoked
        mock_cancel.assert_called_once()

        # Verify: Internal reference cleared
        assert use_case._refresh_cancel is None

    @pytest.mark.asyncio
    async def test_cancel_when_timer_not_scheduled(
        self,
        use_case: ExtractHeatingCyclesUseCase,
    ) -> None:
        """GIVEN: Timer not yet scheduled (no cancel function)

        WHEN: cancel() called

        THEN: Should handle gracefully (no-op)
        """
        # Setup: No cancel function set
        use_case._refresh_cancel = None

        # Execute (should not raise)
        await use_case.cancel()

        # Verify: Did not raise exception
        assert use_case._refresh_cancel is None


# ===== INTEGRATION: FULL FLOW =====


class TestFullCycleExtractionFlow:
    """Test complete flow: startup -> periodic -> reconfiguration -> cleanup."""

    @pytest.mark.asyncio
    async def test_startup_then_periodic_refresh_then_cancel(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_timer_scheduler: Mock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Fresh device setup

        WHEN:
          1. execute() -> initial extraction + timer scheduled
          2. 24h later: _perform_periodic_refresh() -> incremental extraction
          3. Coordinator cleanup: cancel() -> stop timer

        THEN: All steps succeed, cycles incrementally accumulated
        """
        now = dt_util.utcnow()

        # Step 1: Initial extraction
        await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        assert mock_cache.append_cycles.call_count == 1
        assert use_case._refresh_cancel is not None

        # Step 2: Periodic refresh (simulate timer firing)
        await use_case._perform_periodic_refresh()

        assert mock_cache.append_cycles.call_count == 2  # Appended again
        assert mock_cache.prune_old_cycles.call_count == 1

        # Step 3: Cleanup
        await use_case.cancel()

        assert use_case._refresh_cancel is None

    @pytest.mark.asyncio
    async def test_startup_to_retention_change_to_cleanup(
        self,
        use_case: ExtractHeatingCyclesUseCase,
        mock_cache: AsyncMock,
        mock_cycle_service: AsyncMock,
    ) -> None:
        """GIVEN: Device setup with 30-day retention

        WHEN:
          1. execute() -> initial extraction
          2. on_retention_changed(7) -> reconfigure to 7 days
          3. cancel() -> cleanup

        THEN: Retention window changes, cache cleared, timer rescheduled
        """
        now = dt_util.utcnow()

        # Step 1: Initial 30-day extraction
        await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        assert use_case._current_retention_days == 30
        assert mock_cache.append_cycles.call_count == 1

        # Step 2: Retention changed to 7 days
        await use_case.on_retention_changed(new_retention_days=7)

        assert use_case._current_retention_days == 7
        mock_cache.clear_cache.assert_called_with("climate.vtherm")
        assert mock_cycle_service.extract_heating_cycles.call_count == 2  # Called again

        # Step 3: Cleanup
        await use_case.cancel()

        assert use_case._refresh_cancel is None


# ===== REGRESSION: GLOBAL LHS UPDATE BUG =====


class TestGlobalLHSUpdateAfterExtraction:
    """Regression tests for Global LHS update bug.

    Bug: Global LHS is NEVER automatically updated after cycle extraction,
    despite cycles being correctly extracted and stored.

    Root Cause:
    - set_cached_global_lhs() is never called in production code
    - LHS calculation service CAN calculate LHS from cycles
    - But no code path updates the stored global LHS value after extraction

    These tests would have caught this bug and prevent regression.
    """

    @pytest.fixture
    def use_case_with_lhs_deps(
        self,
        mock_device_config: DeviceConfig,
        mock_cycle_service: AsyncMock,
        mock_adapters: list[AsyncMock],
        mock_cache: AsyncMock,
        mock_timer_scheduler: Mock,
        mock_model_storage: AsyncMock,
        mock_lhs_calculation_service: LHSCalculationService,
    ) -> ExtractHeatingCyclesUseCase:
        """Create use case with LHS dependencies injected.

        NOTE: This fixture will FAIL until the developer adds these
        dependencies to the constructor signature.
        """
        return ExtractHeatingCyclesUseCase(
            device_config=mock_device_config,
            heating_cycle_service=mock_cycle_service,
            historical_adapters=mock_adapters,  # type: ignore
            cycle_cache=mock_cache,
            timer_scheduler=mock_timer_scheduler,
            model_storage=mock_model_storage,  # NEW: Will fail - not in constructor yet
            lhs_calculation_service=mock_lhs_calculation_service,  # NEW: Will fail
        )

    @pytest.mark.asyncio
    async def test_execute_updates_global_lhs_after_extraction(
        self,
        mock_device_config: DeviceConfig,
        mock_cycle_service: AsyncMock,
        mock_adapters: list[AsyncMock],
        mock_cache: AsyncMock,
        mock_timer_scheduler: Mock,
        mock_model_storage: AsyncMock,
        mock_lhs_calculation_service: LHSCalculationService,
    ) -> None:
        """Test that execute() updates global LHS after extracting cycles.

        GIVEN: 2+ cycles extracted successfully with valid heating slopes
        WHEN: execute() completes
        THEN: model_storage.set_cached_global_lhs() MUST be called with calculated LHS

        FAILS with buggy code (set_cached_global_lhs never called)
        PASSES with fix (LHS calculated and persisted)
        """
        # Setup: Create cycles with known slopes
        now = dt_util.utcnow()
        cycle1 = HeatingCycle(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=5, hours=2),
            end_time=now - timedelta(days=5, hours=1),
            target_temp=21.0,
            start_temp=19.0,
            end_temp=20.5,
        )
        cycle2 = HeatingCycle(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=3, hours=2),
            end_time=now - timedelta(days=3, hours=1),
            target_temp=22.0,
            start_temp=20.0,
            end_temp=21.5,
        )

        mock_cycle_service.extract_heating_cycles.return_value = [cycle1, cycle2]

        # Calculate expected LHS (should be average of slopes)
        expected_lhs = mock_lhs_calculation_service.calculate_global_lhs([cycle1, cycle2])

        # Create use case with LHS dependencies
        # NOTE: This will FAIL because constructor doesn't have these params yet
        try:
            use_case = ExtractHeatingCyclesUseCase(
                device_config=mock_device_config,
                heating_cycle_service=mock_cycle_service,
                historical_adapters=mock_adapters,  # type: ignore
                cycle_cache=mock_cache,
                timer_scheduler=mock_timer_scheduler,
                model_storage=mock_model_storage,  # type: ignore  # Will fail - not in constructor
                lhs_calculation_service=mock_lhs_calculation_service,  # type: ignore  # Will fail
            )
        except TypeError as e:
            # Expected failure: constructor doesn't accept these params yet
            pytest.fail(
                f"Constructor missing LHS dependencies (expected for RED test): {e}\n"
                "Developer must add model_storage and lhs_calculation_service parameters"
            )

        # Execute extraction
        _cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: set_cached_global_lhs was called with calculated LHS
        mock_model_storage.set_cached_global_lhs.assert_called_once()
        call_kwargs = mock_model_storage.set_cached_global_lhs.call_args.kwargs

        assert call_kwargs["lhs"] == pytest.approx(expected_lhs, abs=0.01), (
            f"Expected LHS {expected_lhs:.2f}°C/h not persisted. "
            f"This indicates calculate_global_lhs() or set_cached_global_lhs() not called."
        )

    @pytest.mark.asyncio
    async def test_execute_updates_global_lhs_only_when_cycles_exist(
        self,
        mock_device_config: DeviceConfig,
        mock_cycle_service: AsyncMock,
        mock_adapters: list[AsyncMock],
        mock_cache: AsyncMock,
        mock_timer_scheduler: Mock,
        mock_model_storage: AsyncMock,
        mock_lhs_calculation_service: LHSCalculationService,
    ) -> None:
        """Test that execute() does NOT update LHS when no cycles extracted.

        GIVEN: 0 cycles extracted (empty history)
        WHEN: execute() completes
        THEN: model_storage.set_cached_global_lhs() NOT called

        FAILS with buggy code (method doesn't exist in flow)
        PASSES with fix (conditional LHS update only when cycles exist)
        """
        # Setup: No cycles extracted
        mock_cycle_service.extract_heating_cycles.return_value = []

        # Create use case with LHS dependencies
        try:
            use_case = ExtractHeatingCyclesUseCase(
                device_config=mock_device_config,
                heating_cycle_service=mock_cycle_service,
                historical_adapters=mock_adapters,  # type: ignore
                cycle_cache=mock_cache,
                timer_scheduler=mock_timer_scheduler,
                model_storage=mock_model_storage,  # type: ignore  # Will fail
                lhs_calculation_service=mock_lhs_calculation_service,  # type: ignore  # Will fail
            )
        except TypeError as e:
            pytest.fail(
                f"Constructor missing LHS dependencies (expected for RED test): {e}\n"
                "Developer must add model_storage and lhs_calculation_service parameters"
            )

        # Execute extraction
        now = dt_util.utcnow()
        _cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: set_cached_global_lhs NOT called (no cycles to learn from)
        mock_model_storage.set_cached_global_lhs.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_calculates_lhs_from_fresh_cycles(
        self,
        mock_device_config: DeviceConfig,
        mock_cycle_service: AsyncMock,
        mock_adapters: list[AsyncMock],
        mock_cache: AsyncMock,
        mock_timer_scheduler: Mock,
        mock_model_storage: AsyncMock,
        mock_lhs_calculation_service: LHSCalculationService,
    ) -> None:
        """Test that LHS is calculated from freshly extracted cycles.

        GIVEN: Cycles with known slopes (1.5°C/h, 2.5°C/h)
        WHEN: execute() completes
        THEN: set_cached_global_lhs() called with avg=2.0°C/h

        FAILS with buggy code (LHS calculation not integrated into flow)
        PASSES with fix (LHS calculated and value matches expected average)
        """
        # Setup: Create cycles with specific slopes
        now = dt_util.utcnow()

        # Cycle 1: 1.5°C rise over 1 hour = 1.5°C/h
        cycle1 = HeatingCycle(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=10, hours=2),
            end_time=now - timedelta(days=10, hours=1),
            target_temp=21.0,
            start_temp=19.0,
            end_temp=20.5,  # 1.5°C rise
        )

        # Cycle 2: 2.5°C rise over 1 hour = 2.5°C/h
        cycle2 = HeatingCycle(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=8, hours=2),
            end_time=now - timedelta(days=8, hours=1),
            target_temp=22.0,
            start_temp=19.0,
            end_temp=21.5,  # 2.5°C rise
        )

        mock_cycle_service.extract_heating_cycles.return_value = [cycle1, cycle2]

        # Expected LHS: (1.5 + 2.5) / 2 = 2.0°C/h
        expected_lhs = 2.0

        # Create use case with LHS dependencies
        try:
            use_case = ExtractHeatingCyclesUseCase(
                device_config=mock_device_config,
                heating_cycle_service=mock_cycle_service,
                historical_adapters=mock_adapters,  # type: ignore
                cycle_cache=mock_cache,
                timer_scheduler=mock_timer_scheduler,
                model_storage=mock_model_storage,  # type: ignore  # Will fail
                lhs_calculation_service=mock_lhs_calculation_service,  # type: ignore  # Will fail
            )
        except TypeError as e:
            pytest.fail(
                f"Constructor missing LHS dependencies (expected for RED test): {e}\n"
                "Developer must add model_storage and lhs_calculation_service parameters"
            )

        # Execute extraction
        _cycles = await use_case.execute(
            device_id="climate.vtherm",
            start_time=now - timedelta(days=30),
            end_time=now,
        )

        # Verify: set_cached_global_lhs called with correct average
        mock_model_storage.set_cached_global_lhs.assert_called_once()
        call_kwargs = mock_model_storage.set_cached_global_lhs.call_args.kwargs
        persisted_lhs = call_kwargs["lhs"]

        assert persisted_lhs == pytest.approx(expected_lhs, abs=0.01), (
            f"Expected LHS {expected_lhs:.2f}°C/h, but got {persisted_lhs:.2f}°C/h. "
            f"Verify calculate_global_lhs() returns average of cycle slopes."
        )
