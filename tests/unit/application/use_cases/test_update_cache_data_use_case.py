"""Tests for UpdateCacheDataUseCase.

STEP 1: Tests verify that the use case correctly delegates to
HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    UpdateCacheDataUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import HeatingCycle


class TestUpdateCacheDataUseCase:
    """Test suite for UpdateCacheDataUseCase.

    STEP 1: Verify delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service._get_cycles_with_cache = AsyncMock(return_value=[])
        service._extract_cycles_from_recorder = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def use_case(self, mock_app_service: Mock) -> UpdateCacheDataUseCase:
        """Create UpdateCacheDataUseCase instance."""
        return UpdateCacheDataUseCase(mock_app_service)

    @pytest.fixture
    def sample_cycles(self) -> list[HeatingCycle]:
        """Create sample heating cycles for testing."""
        return [
            HeatingCycle(
                device_id="climate.test",
                start_time=datetime(2025, 2, 10, 8, 0, 0),
                end_time=datetime(2025, 2, 10, 9, 0, 0),
                start_temp=18.0,
                end_temp=21.0,
                target_temp=21.0,
            ),
            HeatingCycle(
                device_id="climate.test",
                start_time=datetime(2025, 2, 10, 14, 0, 0),
                end_time=datetime(2025, 2, 10, 15, 0, 0),
                start_temp=19.0,
                end_temp=21.0,
                target_temp=21.0,
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_cycles_with_cache_delegates(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that get_cycles_with_cache() delegates to application service.

        STEP 1: Verify delegation pattern with parameters.
        """
        # GIVEN: Parameters for getting cycles
        device_id = "climate.test_vtherm"
        target_time = datetime(2025, 2, 10, 12, 0, 0)

        # WHEN: get_cycles_with_cache is called
        await use_case.get_cycles_with_cache(
            device_id=device_id,
            target_time=target_time,
        )

        # THEN: Application service method is called with same parameters
        mock_app_service._get_cycles_with_cache.assert_called_once_with(
            device_id=device_id,
            target_time=target_time,
        )

    @pytest.mark.asyncio
    async def test_get_cycles_with_cache_returns_cycles(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_app_service: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that get_cycles_with_cache() returns application service result.

        STEP 1: Verify return value passthrough.
        """
        # GIVEN: Application service returns cycles
        mock_app_service._get_cycles_with_cache.return_value = sample_cycles

        # WHEN: get_cycles_with_cache is called
        result = await use_case.get_cycles_with_cache(
            device_id="climate.test",
            target_time=datetime(2025, 2, 10, 12, 0, 0),
        )

        # THEN: Result matches application service return value
        assert result == sample_cycles

    @pytest.mark.asyncio
    async def test_extract_cycles_from_recorder_delegates(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that extract_cycles_from_recorder() delegates to application service.

        STEP 1: Verify delegation pattern with parameters.
        """
        # GIVEN: Parameters for extracting cycles
        device_id = "climate.test_vtherm"
        start_time = datetime(2025, 2, 1, 0, 0, 0)
        end_time = datetime(2025, 2, 10, 23, 59, 59)

        # WHEN: extract_cycles_from_recorder is called
        await use_case.extract_cycles_from_recorder(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
        )

        # THEN: Application service method is called with same parameters
        mock_app_service._extract_cycles_from_recorder.assert_called_once_with(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
        )

    @pytest.mark.asyncio
    async def test_extract_cycles_from_recorder_returns_cycles(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_app_service: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that extract_cycles_from_recorder() returns application service result.

        STEP 1: Verify return value passthrough.
        """
        # GIVEN: Application service returns extracted cycles
        mock_app_service._extract_cycles_from_recorder.return_value = sample_cycles

        # WHEN: extract_cycles_from_recorder is called
        result = await use_case.extract_cycles_from_recorder(
            device_id="climate.test",
            start_time=datetime(2025, 2, 1, 0, 0, 0),
            end_time=datetime(2025, 2, 10, 23, 59, 59),
        )

        # THEN: Result matches application service return value
        assert result == sample_cycles
