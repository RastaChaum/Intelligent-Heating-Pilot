"""Unit tests for cascade error isolation in HeatingCycleLifecycleManager.

These tests verify that errors during LHS updates are isolated and don't
propagate to callers, ensuring partial updates are better than complete failure.

Author: QA Engineer
Purpose: Test error isolation in _trigger_lhs_cascade()
Status: RED - Tests written before implementation (TDD)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestCascadeErrorIsolation:
    """Test error isolation in _trigger_lhs_cascade().

    Regression Prevention:
    These tests ensure that if one LHS calculation fails (global or contextual),
    the other calculation still completes successfully without propagating exceptions.
    """

    @pytest.fixture
    def sample_cycles(self, base_datetime: datetime, heating_cycle_builder) -> list[HeatingCycle]:
        """Create sample heating cycles for testing cascade updates."""
        return [
            heating_cycle_builder(
                base_datetime - timedelta(days=5), duration_hours=2.0, temp_increase=3.0
            ),
            heating_cycle_builder(
                base_datetime - timedelta(days=3), duration_hours=1.5, temp_increase=2.5
            ),
        ]

    @pytest.mark.asyncio
    async def test_global_lhs_error_isolated(
        self,
        heating_cycle_manager_with_lhs_cascade,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that global LHS errors don't propagate and contextual LHS still updates.

        Expected Behavior (FAILS until implemented):
        - Global LHS update throws exception
        - Exception is caught and logged
        - Contextual LHS update still executes
        - No exception propagates to caller

        Bug Prevention:
        Prevents scenario where global LHS failure crashes entire cascade update.
        """
        # ARRANGE: Unpack manager and LHS manager mock
        manager, mock_lhs_manager = heating_cycle_manager_with_lhs_cascade

        # Configure mock: global LHS fails, contextual LHS succeeds
        mock_lhs_manager.update_global_lhs_from_cycles = AsyncMock(
            side_effect=RuntimeError("Database connection failed")
        )
        mock_lhs_manager.update_contextual_lhs_from_cycles = AsyncMock()

        # ACT: Call cascade (should NOT raise exception)
        # This will FAIL until _trigger_lhs_cascade() implements error isolation
        await manager._trigger_lhs_cascade(sample_cycles)

        # ASSERT: Contextual LHS should still be called despite global LHS error
        mock_lhs_manager.update_global_lhs_from_cycles.assert_called_once_with(sample_cycles)
        mock_lhs_manager.update_contextual_lhs_from_cycles.assert_called_once_with(sample_cycles)

    @pytest.mark.asyncio
    async def test_contextual_lhs_error_isolated(
        self,
        heating_cycle_manager_with_lhs_cascade,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that contextual LHS errors don't propagate and global LHS still updates.

        Expected Behavior (FAILS until implemented):
        - Global LHS update succeeds
        - Contextual LHS update throws exception
        - Exception is caught and logged
        - No exception propagates to caller

        Bug Prevention:
        Prevents scenario where contextual LHS failure prevents global LHS from updating.
        """
        # ARRANGE: Unpack manager and LHS manager mock
        manager, mock_lhs_manager = heating_cycle_manager_with_lhs_cascade

        # Configure mock: global LHS succeeds, contextual LHS fails
        mock_lhs_manager.update_global_lhs_from_cycles = AsyncMock()
        mock_lhs_manager.update_contextual_lhs_from_cycles = AsyncMock(
            side_effect=ValueError("Invalid hour range")
        )

        # ACT: Call cascade (should NOT raise exception)
        # This will FAIL until _trigger_lhs_cascade() implements error isolation
        await manager._trigger_lhs_cascade(sample_cycles)

        # ASSERT: Global LHS should complete successfully
        mock_lhs_manager.update_global_lhs_from_cycles.assert_called_once_with(sample_cycles)
        mock_lhs_manager.update_contextual_lhs_from_cycles.assert_called_once_with(sample_cycles)

    @pytest.mark.asyncio
    async def test_both_errors_isolated(
        self,
        heating_cycle_manager_with_lhs_cascade,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that both global AND contextual errors are isolated.

        Expected Behavior (FAILS until implemented):
        - Global LHS update throws exception
        - Contextual LHS update throws exception
        - Both exceptions are caught and logged
        - No exception propagates to caller

        Bug Prevention:
        Prevents complete cascade failure when both calculations have errors.
        """
        # ARRANGE: Unpack manager and LHS manager mock
        manager, mock_lhs_manager = heating_cycle_manager_with_lhs_cascade

        # Configure mock: both fail
        mock_lhs_manager.update_global_lhs_from_cycles = AsyncMock(
            side_effect=RuntimeError("Global calculation failed")
        )
        mock_lhs_manager.update_contextual_lhs_from_cycles = AsyncMock(
            side_effect=RuntimeError("Contextual calculation failed")
        )

        # ACT: Call cascade (should NOT raise exception)
        # This will FAIL until _trigger_lhs_cascade() implements error isolation
        await manager._trigger_lhs_cascade(sample_cycles)

        # ASSERT: Both should be attempted despite failures
        mock_lhs_manager.update_global_lhs_from_cycles.assert_called_once_with(sample_cycles)
        mock_lhs_manager.update_contextual_lhs_from_cycles.assert_called_once_with(sample_cycles)

    @pytest.mark.asyncio
    async def test_both_succeed_no_errors(
        self,
        heating_cycle_manager_with_lhs_cascade,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test happy path: both LHS updates succeed without errors.

        Expected Behavior (PASSES immediately):
        - Global LHS update succeeds
        - Contextual LHS update succeeds
        - No exceptions raised

        Bug Prevention:
        Ensures error isolation doesn't break normal success path.
        """
        # ARRANGE: Unpack manager and LHS manager mock
        manager, mock_lhs_manager = heating_cycle_manager_with_lhs_cascade

        # Configure mock: both succeed
        mock_lhs_manager.update_global_lhs_from_cycles = AsyncMock()
        mock_lhs_manager.update_contextual_lhs_from_cycles = AsyncMock()

        # ACT: Call cascade (should succeed without exception)
        await manager._trigger_lhs_cascade(sample_cycles)

        # ASSERT: Both should complete successfully
        mock_lhs_manager.update_global_lhs_from_cycles.assert_called_once_with(sample_cycles)
        mock_lhs_manager.update_contextual_lhs_from_cycles.assert_called_once_with(sample_cycles)

    @pytest.mark.asyncio
    async def test_no_lhs_manager_skips_cascade(
        self,
        device_config,
        mock_heating_cycle_service,
        mock_historical_adapter,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that cascade is skipped when no LHS manager is attached.

        Expected Behavior (PASSES immediately):
        - No LHS manager configured
        - Cascade call returns immediately without error
        - No calculations attempted

        Bug Prevention:
        Ensures optional LHS manager doesn't cause errors when not present.
        """
        # ARRANGE: Create manager without LHS manager
        manager = HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=mock_heating_cycle_service,
            historical_adapters=[mock_historical_adapter],
            heating_cycle_storage=None,
            timer_scheduler=None,
            lhs_storage=None,
            lhs_lifecycle_manager=None,  # No LHS manager
        )

        # ACT: Call cascade (should return immediately without error)
        await manager._trigger_lhs_cascade(sample_cycles)

        # ASSERT: No exceptions raised (test passes by not raising)
        # If we get here without exception, test passed
        assert manager._lhs_lifecycle_manager is None
