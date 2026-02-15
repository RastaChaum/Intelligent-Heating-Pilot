"""Unit tests for cascade error isolation in HeatingCycleLifecycleManager.

These tests verify that errors during LHS updates are isolated and don't
propagate to callers, ensuring partial updates are better than complete failure.

Author: QA Engineer
Purpose: Test error isolation in _trigger_lhs_cascade()
Status: RED - Tests written before implementation (TDD)
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestCascadeErrorIsolation:
    """Test edge cases for _trigger_lhs_cascade().

    NOTE: Happy paths and error isolation scenarios are covered by BDD tests
    in tests/features/cache_cascade.feature. These unit tests cover only
    technical edge cases not expressible in Gherkin.

    Regression Prevention:
    Ensures cascade handles optional dependencies gracefully.
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
