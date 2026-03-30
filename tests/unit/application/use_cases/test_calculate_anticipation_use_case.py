"""Tests for CalculateAnticipationUseCase.

Tests verify that the use case correctly calculates anticipation data
using domain dependencies (scheduler_reader, environment_reader, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
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
from custom_components.intelligent_heating_pilot.domain.services import (
    DeadTimeCalculationService,
    PredictionService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    PredictionResult,
    ScheduledTimeslot,
)


class TestCalculateAnticipationUseCase:
    """Test suite for CalculateAnticipationUseCase with domain dependencies."""

    @pytest.fixture
    def mock_scheduler_reader(self) -> Mock:
        """Create mock scheduler reader."""
        reader = Mock()
        reader.get_next_timeslot = AsyncMock(return_value=None)
        return reader

    @pytest.fixture
    def mock_environment_reader(self) -> Mock:
        """Create mock environment reader."""
        reader = Mock()
        reader.get_current_environment = AsyncMock(
            return_value=EnvironmentState(
                indoor_temperature=19.0,
                outdoor_temp=5.0,
                indoor_humidity=60.0,
                cloud_coverage=50.0,
                timestamp=datetime(2025, 2, 10, 6, 0, 0, tzinfo=timezone.utc),
            )
        )
        return reader

    @pytest.fixture
    def mock_climate_data_reader(self) -> Mock:
        """Create mock climate data reader."""
        reader = Mock()
        reader.get_vtherm_entity_id = Mock(return_value="climate.test_vtherm")
        reader.get_current_slope = Mock(return_value=None)
        reader.is_heating_active = Mock(return_value=False)
        return reader

    @pytest.fixture
    def mock_heating_cycle_manager(self) -> Mock:
        """Create mock heating cycle lifecycle manager."""
        mgr = AsyncMock(spec=HeatingCycleLifecycleManager)
        mgr.get_cycles_for_target_time = AsyncMock(return_value=[])
        return mgr

    @pytest.fixture
    def mock_lhs_lifecycle_manager(self) -> Mock:
        """Create mock LHS lifecycle manager."""
        mgr = AsyncMock(spec=LhsLifecycleManager)
        mgr.get_contextual_lhs = AsyncMock(return_value=2.0)
        mgr.get_global_lhs = AsyncMock(return_value=2.0)
        return mgr

    @pytest.fixture
    def mock_prediction_service(self) -> Mock:
        """Create mock prediction service."""
        svc = Mock(spec=PredictionService)
        svc.predict_heating_time = Mock(
            return_value=PredictionResult(
                anticipated_start_time=datetime(2025, 2, 10, 9, 0, 0, tzinfo=timezone.utc),
                estimated_duration_minutes=60.0,
                confidence_level=0.8,
                learned_heating_slope=2.0,
            )
        )
        return svc

    @pytest.fixture
    def mock_dead_time_calculator(self) -> Mock:
        """Create mock dead time calculator."""
        calc = Mock(spec=DeadTimeCalculationService)
        calc.calculate_average_dead_time = Mock(return_value=None)
        return calc

    @pytest.fixture
    def use_case(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator: Mock,
    ) -> CalculateAnticipationUseCase:
        """Create CalculateAnticipationUseCase instance with domain dependencies."""
        return CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator,
            auto_learning=True,
            default_dead_time_minutes=0.0,
        )

    @pytest.mark.asyncio
    async def test_happy_path_valid_timeslot_returns_prediction(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_scheduler_reader: Mock,
        mock_prediction_service: Mock,
    ) -> None:
        """Test that valid timeslot produces anticipation data with prediction."""
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc)
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        result = await use_case.calculate_anticipation_datas()

        assert result is not None
        assert result["anticipated_start_time"] is not None
        assert result["next_schedule_time"] == target_time
        assert result["next_target_temperature"] == 21.0
        mock_prediction_service.predict_heating_time.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_scheduler_reader_returns_empty_data(
        self,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator: Mock,
    ) -> None:
        """Test that no scheduler reader and no target_time returns empty data structure."""
        use_case = CalculateAnticipationUseCase(
            scheduler_reader=None,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator,
        )

        result = await use_case.calculate_anticipation_datas()

        assert result["anticipated_start_time"] is None
        mock_prediction_service.predict_heating_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_timeslot_returns_empty_data(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_scheduler_reader: Mock,
        mock_prediction_service: Mock,
    ) -> None:
        """Test that no scheduled timeslot returns empty data structure."""
        mock_scheduler_reader.get_next_timeslot.return_value = None

        result = await use_case.calculate_anticipation_datas()

        assert result["anticipated_start_time"] is None
        mock_prediction_service.predict_heating_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_target_time_without_target_temp_returns_empty(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_prediction_service: Mock,
    ) -> None:
        """Test that providing target_time without target_temp returns empty data."""
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc)

        result = await use_case.calculate_anticipation_datas(
            target_time=target_time,
            target_temp=None,
        )

        assert result["anticipated_start_time"] is None
        mock_prediction_service.predict_heating_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_target_time_with_target_temp_bypasses_scheduler(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_scheduler_reader: Mock,
        mock_prediction_service: Mock,
    ) -> None:
        """Test that providing target_time and target_temp bypasses scheduler reader."""
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc)

        result = await use_case.calculate_anticipation_datas(
            target_time=target_time,
            target_temp=22.0,
        )

        mock_scheduler_reader.get_next_timeslot.assert_not_called()
        mock_prediction_service.predict_heating_time.assert_called_once()
        assert result["anticipated_start_time"] is not None


class TestCalculateAnticipationUseCaseDeadTimeHydration:
    """Regression tests for dead time startup hydration.

    Bug: After HA restart, no cycles are available in memory until cycle extraction
    completes. CalculateAnticipationUseCase fell back to default_dead_time_minutes
    (0.0), which was then persisted by async_update(), overwriting the stored
    learned dead time and causing the dead time sensor to display 0.

    These tests ensure the persisted learned dead time is used as a fallback
    when auto_learning=True but no cycles are available yet.
    """

    @pytest.fixture
    def mock_scheduler_reader(self) -> Mock:
        """Create mock scheduler reader that returns a valid timeslot."""
        reader = Mock()
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc)
        reader.get_next_timeslot = AsyncMock(
            return_value=ScheduledTimeslot(
                target_time=target_time,
                target_temp=21.0,
                timeslot_id="morning",
                scheduler_entity="schedule.heating",
            )
        )
        return reader

    @pytest.fixture
    def mock_environment_reader(self) -> Mock:
        reader = Mock()
        reader.get_current_environment = AsyncMock(
            return_value=EnvironmentState(
                indoor_temperature=19.0,
                outdoor_temp=5.0,
                indoor_humidity=60.0,
                cloud_coverage=50.0,
                timestamp=datetime(2025, 2, 10, 6, 0, 0, tzinfo=timezone.utc),
            )
        )
        return reader

    @pytest.fixture
    def mock_climate_data_reader(self) -> Mock:
        reader = Mock()
        reader.get_vtherm_entity_id = Mock(return_value="climate.test_vtherm")
        return reader

    @pytest.fixture
    def mock_heating_cycle_manager_no_cycles(self) -> Mock:
        """Simulate no cycles available in memory (as on startup before extraction)."""
        mgr = AsyncMock(spec=HeatingCycleLifecycleManager)
        mgr.get_cycles_for_target_time = AsyncMock(return_value=[])
        return mgr

    @pytest.fixture
    def mock_lhs_lifecycle_manager(self) -> Mock:
        mgr = AsyncMock(spec=LhsLifecycleManager)
        mgr.get_contextual_lhs = AsyncMock(return_value=2.0)
        mgr.get_global_lhs = AsyncMock(return_value=2.0)
        return mgr

    @pytest.fixture
    def mock_prediction_service(self) -> Mock:
        svc = Mock(spec=PredictionService)
        svc.predict_heating_time = Mock(
            return_value=PredictionResult(
                anticipated_start_time=datetime(2025, 2, 10, 9, 0, 0, tzinfo=timezone.utc),
                estimated_duration_minutes=60.0,
                confidence_level=0.8,
                learned_heating_slope=2.0,
            )
        )
        return svc

    @pytest.fixture
    def mock_dead_time_calculator_no_result(self) -> Mock:
        calc = Mock(spec=DeadTimeCalculationService)
        calc.calculate_average_dead_time = Mock(return_value=None)
        return calc

    @pytest.fixture
    def mock_lhs_storage_with_value(self) -> Mock:
        """Mock storage that returns a previously persisted learned dead time (6.5 min)."""
        storage = Mock()
        storage.get_learned_dead_time = AsyncMock(return_value=6.5)
        return storage

    @pytest.fixture
    def mock_lhs_storage_empty(self) -> Mock:
        """Mock storage that has no previously persisted dead time."""
        storage = Mock()
        storage.get_learned_dead_time = AsyncMock(return_value=None)
        return storage

    @pytest.mark.asyncio
    async def test_uses_persisted_dead_time_when_no_cycles_on_startup(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager_no_cycles: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator_no_result: Mock,
        mock_lhs_storage_with_value: Mock,
    ) -> None:
        """Persisted learned dead time is used when auto_learning=True and no cycles available.

        Regression test: After HA restart, before cycle extraction completes, the
        use case must fall back to the persisted learned dead time (6.5 min) instead
        of the configured default (0.0 min). Without the fix this test fails because
        dead_time in the result would be 0.0 (the default).
        """
        use_case = CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager_no_cycles,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator_no_result,
            auto_learning=True,
            default_dead_time_minutes=0.0,
            lhs_storage=mock_lhs_storage_with_value,
        )

        result = await use_case.calculate_anticipation_datas()

        # FAILS before fix: dead_time would be 0.0 (configured default)
        # PASSES after fix: dead_time is 6.5 (persisted learned value)
        assert result["dead_time"] == pytest.approx(6.5)
        mock_lhs_storage_with_value.get_learned_dead_time.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_configured_default_when_no_persisted_value(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager_no_cycles: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator_no_result: Mock,
        mock_lhs_storage_empty: Mock,
    ) -> None:
        """Configured default is used when no cycles and no persisted dead time exists.

        When the integration is freshly installed (auto_learning=True but nothing
        has been learned yet), the configured default_dead_time_minutes is used.
        """
        use_case = CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager_no_cycles,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator_no_result,
            auto_learning=True,
            default_dead_time_minutes=5.0,
            lhs_storage=mock_lhs_storage_empty,
        )

        result = await use_case.calculate_anticipation_datas()

        assert result["dead_time"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_uses_configured_default_when_no_lhs_storage_provided(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager_no_cycles: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator_no_result: Mock,
    ) -> None:
        """Falls back to configured default when no lhs_storage is provided."""
        use_case = CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager_no_cycles,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator_no_result,
            auto_learning=True,
            default_dead_time_minutes=3.0,
            lhs_storage=None,
        )

        result = await use_case.calculate_anticipation_datas()

        assert result["dead_time"] == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_auto_learning_disabled_always_uses_configured_default(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_heating_cycle_manager_no_cycles: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_dead_time_calculator_no_result: Mock,
        mock_lhs_storage_with_value: Mock,
    ) -> None:
        """When auto_learning=False, persisted dead time is never consulted.

        The configured dead_time_minutes is always used regardless of what is
        stored, matching the expected behavior documented in the issue comment.
        """
        use_case = CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mock_heating_cycle_manager_no_cycles,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=mock_dead_time_calculator_no_result,
            auto_learning=False,
            default_dead_time_minutes=5.0,
            lhs_storage=mock_lhs_storage_with_value,
        )

        result = await use_case.calculate_anticipation_datas()

        # Storage should NOT be consulted when auto_learning=False
        assert result["dead_time"] == pytest.approx(5.0)
        mock_lhs_storage_with_value.get_learned_dead_time.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_learned_from_cycles_takes_precedence_over_persisted(
        self,
        mock_scheduler_reader: Mock,
        mock_environment_reader: Mock,
        mock_climate_data_reader: Mock,
        mock_lhs_lifecycle_manager: Mock,
        mock_prediction_service: Mock,
        mock_lhs_storage_with_value: Mock,
    ) -> None:
        """Dead time computed from in-memory cycles overrides the persisted value.

        When cycles are available and yield a valid dead time, that value is used
        directly without reading from storage.
        """
        from datetime import timedelta

        from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
            HeatingCycle,
        )

        base = datetime(2025, 2, 9, 8, 0, 0, tzinfo=timezone.utc)
        cycle = HeatingCycle(
            device_id="climate.test",
            start_time=base,
            end_time=base + timedelta(hours=2),
            target_temp=21.0,
            end_temp=20.5,
            start_temp=18.0,
            dead_time_cycle_minutes=8.0,
        )

        mgr_with_cycles = AsyncMock(spec=HeatingCycleLifecycleManager)
        mgr_with_cycles.get_cycles_for_target_time = AsyncMock(return_value=[cycle])

        calc = Mock(spec=DeadTimeCalculationService)
        calc.calculate_average_dead_time = Mock(return_value=8.0)

        use_case = CalculateAnticipationUseCase(
            scheduler_reader=mock_scheduler_reader,
            environment_reader=mock_environment_reader,
            climate_data_reader=mock_climate_data_reader,
            heating_cycle_manager=mgr_with_cycles,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
            prediction_service=mock_prediction_service,
            dead_time_calculator=calc,
            auto_learning=True,
            default_dead_time_minutes=0.0,
            lhs_storage=mock_lhs_storage_with_value,
        )

        result = await use_case.calculate_anticipation_datas()

        # Dead time from cycles (8.0) should be used, not the stored value (6.5)
        assert result["dead_time"] == pytest.approx(8.0)
        # Storage should NOT be read when cycles provide a valid dead time
        mock_lhs_storage_with_value.get_learned_dead_time.assert_not_awaited()
