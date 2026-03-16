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
