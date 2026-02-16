"""Tests for UpdateCacheDataUseCase.

Tests verify that the use case correctly delegates to
IHeatingCycleStorage, ILhsStorage, and LhsLifecycleManager.
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

    Verifies delegation to IHeatingCycleStorage, ILhsStorage, and LhsLifecycleManager.
    """

    @pytest.fixture
    def mock_cycle_storage(self) -> Mock:
        """Create mock IHeatingCycleStorage."""
        storage = Mock()
        storage.get_cache_data = AsyncMock(return_value=None)
        storage.append_cycles = AsyncMock()
        storage.prune_old_cycles = AsyncMock()
        storage.clear_cache = AsyncMock()
        return storage

    @pytest.fixture
    def mock_lhs_storage(self) -> Mock:
        """Create mock ILhsStorage."""
        storage = Mock()
        storage.clear_slopes_datas = AsyncMock()
        return storage

    @pytest.fixture
    def mock_lhs_lifecycle_manager(self) -> Mock:
        """Create mock LhsLifecycleManager."""
        manager = Mock()
        manager.update_global_lhs_from_cache = AsyncMock()
        return manager

    @pytest.fixture
    def use_case(
        self,
        mock_cycle_storage: Mock,
        mock_lhs_storage: Mock,
        mock_lhs_lifecycle_manager: Mock,
    ) -> UpdateCacheDataUseCase:
        """Create UpdateCacheDataUseCase instance."""
        return UpdateCacheDataUseCase(
            mock_cycle_storage, mock_lhs_storage, mock_lhs_lifecycle_manager
        )

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
    async def test_get_cache_data_delegates(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_cycle_storage: Mock,
    ) -> None:
        """Test that get_cache_data() delegates to cycle storage.

        Verifies delegation pattern with parameters.
        """
        # GIVEN: Parameters for getting cache data
        device_id = "climate.test_vtherm"

        # WHEN: get_cache_data is called
        await use_case.get_cache_data(device_id=device_id)

        # THEN: Cycle storage method is called with same parameters
        mock_cycle_storage.get_cache_data.assert_called_once_with(device_id)

    @pytest.mark.asyncio
    async def test_get_cache_data_returns_result(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_cycle_storage: Mock,
    ) -> None:
        """Test that get_cache_data() returns storage result.

        Verifies return value passthrough.
        """
        # GIVEN: Storage returns cache data
        mock_cache_data = Mock()
        mock_cycle_storage.get_cache_data.return_value = mock_cache_data

        # WHEN: get_cache_data is called
        result = await use_case.get_cache_data(device_id="climate.test")

        # THEN: Result matches storage return value
        assert result == mock_cache_data

    @pytest.mark.asyncio
    async def test_append_cycles_delegates(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_cycle_storage: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that append_cycles() delegates to cycle storage.

        Verifies delegation pattern with parameters.
        """
        # GIVEN: Parameters for appending cycles
        device_id = "climate.test_vtherm"
        reference_time = datetime(2025, 2, 10, 12, 0, 0)

        # WHEN: append_cycles is called
        await use_case.append_cycles(
            device_id=device_id,
            cycles=sample_cycles,
            reference_time=reference_time,
        )

        # THEN: Cycle storage append_cycles is called
        mock_cycle_storage.append_cycles.assert_called_once_with(
            device_id, sample_cycles, reference_time
        )

    @pytest.mark.asyncio
    async def test_append_cycles_triggers_prune(
        self,
        use_case: UpdateCacheDataUseCase,
        mock_cycle_storage: Mock,
        mock_lhs_lifecycle_manager: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that append_cycles() also prunes old cycles and recalculates LHS.

        Verifies that the full workflow is triggered.
        """
        # GIVEN: Parameters for appending cycles
        device_id = "climate.test_vtherm"
        reference_time = datetime(2025, 2, 10, 12, 0, 0)

        # WHEN: append_cycles is called
        await use_case.append_cycles(
            device_id=device_id,
            cycles=sample_cycles,
            reference_time=reference_time,
        )

        # THEN: Prune is also called (via prune_old_cycles path)
        mock_cycle_storage.prune_old_cycles.assert_called_once_with(
            device_id, reference_time
        )
        # And LHS is recalculated
        mock_lhs_lifecycle_manager.update_global_lhs_from_cache.assert_called_once_with(
            device_id
        )
