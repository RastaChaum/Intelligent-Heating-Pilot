"""Tests for ResetLearningUseCase.

Tests verify that the use case correctly delegates to
ILhsStorage and IHeatingCycleStorage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ResetLearningUseCase,
)


class TestResetLearningUseCase:
    """Test suite for ResetLearningUseCase.

    Verifies delegation to ILhsStorage and IHeatingCycleStorage.
    """

    @pytest.fixture
    def mock_lhs_storage(self) -> Mock:
        """Create mock ILhsStorage."""
        storage = Mock()
        storage.clear_slopes_datas = AsyncMock()
        return storage

    @pytest.fixture
    def mock_cycle_storage(self) -> Mock:
        """Create mock IHeatingCycleStorage."""
        storage = Mock()
        storage.clear_heatingcycle_datas = AsyncMock()
        return storage

    @pytest.fixture
    def use_case(
        self, mock_lhs_storage: Mock, mock_cycle_storage: Mock
    ) -> ResetLearningUseCase:
        """Create ResetLearningUseCase instance."""
        return ResetLearningUseCase(mock_lhs_storage, mock_cycle_storage)

    @pytest.mark.asyncio
    async def test_execute_delegates_to_storages(
        self,
        use_case: ResetLearningUseCase,
        mock_lhs_storage: Mock,
        mock_cycle_storage: Mock,
    ) -> None:
        """Test that reset_all_learning_data() delegates to both storages.

        Verifies delegation pattern.
        """
        # GIVEN: Use case initialized with mock storages
        device_id = "climate.test_vtherm"

        # WHEN: reset_all_learning_data is called
        await use_case.reset_all_learning_data(device_id)

        # THEN: Both storages are cleared
        mock_lhs_storage.clear_slopes_datas.assert_called_once()
        mock_cycle_storage.clear_heatingcycle_datas.assert_called_once_with(device_id)

    @pytest.mark.asyncio
    async def test_execute_no_return_value(
        self,
        use_case: ResetLearningUseCase,
    ) -> None:
        """Test that reset_all_learning_data() has no return value.

        Verifies void return.
        """
        # WHEN: reset_all_learning_data is called
        result = await use_case.reset_all_learning_data("climate.test_vtherm")

        # THEN: Result is None
        assert result is None
