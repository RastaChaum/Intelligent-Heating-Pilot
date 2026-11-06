"""Tests for ControlPreheatingUseCase.

Tests verify that the use case correctly delegates to ISchedulerCommander
and tracks preheating state.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)
from custom_components.intelligent_heating_pilot.domain.constants import (
    ACTION_EFFECT_TIMEOUT_SECONDS,
)

_USE_CASE_MODULE = (
    "custom_components.intelligent_heating_pilot.application.use_cases.control_preheating_use_case"
)


class TestControlPreheatingUseCase:
    """Test suite for ControlPreheatingUseCase.

    Verifies delegation to ISchedulerCommander and internal state tracking.
    """

    @pytest.fixture
    def mock_scheduler_commander(self) -> Mock:
        """Create mock ISchedulerCommander."""
        commander = Mock()
        commander.run_action = AsyncMock(return_value=True)
        commander.cancel_action = AsyncMock()
        return commander

    @pytest.fixture
    def use_case(self, mock_scheduler_commander: Mock) -> ControlPreheatingUseCase:
        """Create ControlPreheatingUseCase instance."""
        return ControlPreheatingUseCase(mock_scheduler_commander)

    @pytest.mark.asyncio
    async def test_cancel_preheating_delegates_to_commander(
        self,
        use_case: ControlPreheatingUseCase,
        mock_scheduler_commander: Mock,
    ) -> None:
        """Test that cancel_preheating() delegates to scheduler commander.

        Verifies delegation pattern when preheating is active.
        """
        # GIVEN: Preheating is active
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        scheduler_entity_id = "schedule.heating"
        await use_case.start_preheating(
            target_time=target_time,
            target_temp=21.0,
            scheduler_entity_id=scheduler_entity_id,
        )

        # WHEN: cancel_preheating is called
        await use_case.cancel_preheating(scheduler_entity_id)

        # THEN: Commander cancel_action is called
        mock_scheduler_commander.cancel_action.assert_called_once_with(scheduler_entity_id)

    @pytest.mark.asyncio
    async def test_start_preheating_delegates_to_commander(
        self,
        use_case: ControlPreheatingUseCase,
        mock_scheduler_commander: Mock,
    ) -> None:
        """Test that start_preheating() delegates to scheduler commander.

        Verifies delegation with parameters.
        """
        # GIVEN: Parameters for starting preheating
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        target_temp = 21.0
        scheduler_entity_id = "schedule.heating"

        # WHEN: start_preheating is called
        await use_case.start_preheating(
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
        )

        # THEN: Commander run_action is called with correct parameters
        mock_scheduler_commander.run_action.assert_called_once_with(
            target_time, scheduler_entity_id
        )

    def test_is_preheating_active_returns_state(
        self,
        use_case: ControlPreheatingUseCase,
    ) -> None:
        """Test that is_preheating_active() returns internal state.

        Verifies state tracking.
        """
        # GIVEN: No preheating started
        # WHEN: is_preheating_active is called
        result = use_case.is_preheating_active()

        # THEN: Result is False
        assert result is False

    @pytest.mark.asyncio
    async def test_is_preheating_active_after_start(
        self,
        use_case: ControlPreheatingUseCase,
        mock_scheduler_commander: Mock,
    ) -> None:
        """Test that is_preheating_active() returns True after start."""
        # GIVEN: Preheating has been started
        await use_case.start_preheating(
            target_time=datetime(2025, 2, 10, 11, 0, 0),
            target_temp=21.0,
            scheduler_entity_id="schedule.heating",
        )

        # WHEN/THEN
        assert use_case.is_preheating_active() is True

    def test_get_preheating_target_time_returns_state(
        self,
        use_case: ControlPreheatingUseCase,
    ) -> None:
        """Test that get_preheating_target_time() returns internal state.

        Verifies state tracking.
        """
        # GIVEN: No preheating started
        # WHEN: get_preheating_target_time is called
        result = use_case.get_preheating_target_time()

        # THEN: Result is None
        assert result is None

    @pytest.mark.asyncio
    async def test_get_preheating_target_time_after_start(
        self,
        use_case: ControlPreheatingUseCase,
        mock_scheduler_commander: Mock,
    ) -> None:
        """Test that get_preheating_target_time() returns time after start."""
        # GIVEN: Preheating has been started
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        await use_case.start_preheating(
            target_time=target_time,
            target_temp=21.0,
            scheduler_entity_id="schedule.heating",
        )

        # WHEN/THEN
        assert use_case.get_preheating_target_time() == target_time


class TestStartPreheatingVerification:
    """Tests for the scheduler-action-effect verification added for issue #64.

    Without a climate_data_reader, behavior is unchanged (see
    TestControlPreheatingUseCase above) — these tests cover the new verified path.
    """

    @pytest.fixture
    def mock_scheduler_commander(self) -> Mock:
        commander = Mock()
        commander.run_action = AsyncMock(return_value=True)
        commander.cancel_action = AsyncMock()
        return commander

    @pytest.fixture
    def mock_climate_data_reader(self) -> Mock:
        reader = Mock()
        reader.get_target_temperature = Mock(return_value=20.0)
        reader.wait_for_state_change = AsyncMock(return_value=False)  # timeout: no change
        return reader

    @pytest.mark.asyncio
    async def test_confirmed_match_returns_true_and_marks_active(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A matching resulting temperature confirms success and marks preheating active."""
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )
        target_time = datetime(2025, 2, 10, 11, 0, 0)

        result = await use_case.start_preheating(target_time, 20.0, "switch.heating")

        assert result is True
        assert use_case.is_preheating_active() is True
        assert use_case.get_preheating_target_time() == target_time
        assert use_case.get_active_scheduler_entity() == "switch.heating"

    @pytest.mark.asyncio
    async def test_confirmed_mismatch_returns_false_without_mutating_state(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A confirmed mismatch (conditions blocked the action) returns False and leaves
        preheating state untouched, so a same-cycle fallback is not blocked (#64)."""
        mock_climate_data_reader.get_target_temperature.return_value = 17.0  # unchanged eco temp
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )
        target_time = datetime(2025, 2, 10, 11, 0, 0)

        result = await use_case.start_preheating(target_time, 20.0, "switch.heating")

        assert result is False
        assert use_case.is_preheating_active() is False
        assert use_case.get_preheating_target_time() is None
        assert use_case.get_active_scheduler_entity() is None

    @pytest.mark.asyncio
    async def test_unreadable_state_treated_as_success(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """An unreadable VTherm state cannot prove failure, so it is treated as success."""
        mock_climate_data_reader.get_target_temperature.return_value = None
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2025, 2, 10, 11, 0, 0), 20.0, "switch.heating"
        )

        assert result is True
        assert use_case.is_preheating_active() is True

    @pytest.mark.asyncio
    async def test_native_schedule_skips_verification(self, mock_climate_data_reader: Mock) -> None:
        """A native schedule (attempted=False) is never verified against the mismatch."""
        commander = Mock()
        commander.run_action = AsyncMock(return_value=False)
        use_case = ControlPreheatingUseCase(commander, climate_data_reader=mock_climate_data_reader)

        result = await use_case.start_preheating(
            datetime(2025, 2, 10, 11, 0, 0), 20.0, "schedule.heating"
        )

        assert result is True
        assert use_case.is_preheating_active() is True
        mock_climate_data_reader.get_target_temperature.assert_not_called()

    @pytest.mark.asyncio
    async def test_within_tolerance_counts_as_match(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A tiny floating-point difference within tolerance still counts as success."""
        mock_climate_data_reader.get_target_temperature.return_value = 20.03
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2025, 2, 10, 11, 0, 0), 20.0, "switch.heating"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_without_climate_data_reader_skips_verification(
        self, mock_scheduler_commander: Mock
    ) -> None:
        """Omitting climate_data_reader (existing callers) preserves today's behavior exactly."""
        use_case = ControlPreheatingUseCase(mock_scheduler_commander)

        result = await use_case.start_preheating(
            datetime(2025, 2, 10, 11, 0, 0), 20.0, "switch.heating"
        )

        assert result is True
        assert use_case.is_preheating_active() is True


class TestStartPreheatingWaitsForThermostat:
    """scheduler-component returns from run_action before the VTherm has changed (#256).

    A mismatch is only confirmed once the VTherm had the chance to apply the
    action: IHP waits for its state changes, up to the action effect timeout.
    """

    @pytest.fixture
    def mock_scheduler_commander(self) -> Mock:
        commander = Mock()
        commander.run_action = AsyncMock(return_value=True)
        commander.cancel_action = AsyncMock()
        return commander

    @pytest.fixture
    def mock_climate_data_reader(self) -> Mock:
        reader = Mock()
        reader.get_target_temperature = Mock(return_value=18.0)  # eco, before the action
        reader.wait_for_state_change = AsyncMock(return_value=False)
        return reader

    @staticmethod
    def _apply_on_state_change(reader: Mock, *targets: float) -> None:
        """Make each awaited state change expose the next target temperature."""
        pending = list(targets)

        async def _wait(timeout_seconds: float) -> bool:
            if not pending:
                return False
            reader.get_target_temperature.return_value = pending.pop(0)
            return True

        reader.wait_for_state_change.side_effect = _wait

    @pytest.mark.asyncio
    async def test_action_applied_after_run_action_is_confirmed(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """The setpoint applied a moment after run_action confirms the preheat."""
        self._apply_on_state_change(mock_climate_data_reader, 20.0)
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
        )

        assert result is True
        assert use_case.is_preheating_active() is True
        assert use_case.get_active_scheduler_entity() == "switch.weekend"
        mock_climate_data_reader.wait_for_state_change.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_immediate_match_does_not_wait(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A target already applied when run_action returns is confirmed at once."""
        mock_climate_data_reader.get_target_temperature.return_value = 20.0
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
        )

        assert result is True
        mock_climate_data_reader.wait_for_state_change.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_first_wait_lasts_the_action_effect_timeout(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """With no state change, IHP waits the whole timeout, then reports blocked."""
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        with patch(f"{_USE_CASE_MODULE}.monotonic", return_value=100.0):
            result = await use_case.start_preheating(
                datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
            )

        assert result is False
        assert use_case.is_preheating_active() is False
        mock_climate_data_reader.wait_for_state_change.assert_awaited_once_with(
            ACTION_EFFECT_TIMEOUT_SECONDS
        )

    @pytest.mark.asyncio
    async def test_preset_then_temperature_updates_are_followed(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A state change that does not match yet (preset first) keeps IHP waiting."""
        self._apply_on_state_change(mock_climate_data_reader, 18.0, 20.0)
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
        )

        assert result is True
        assert mock_climate_data_reader.wait_for_state_change.await_count == 2

    @pytest.mark.asyncio
    async def test_unrelated_changes_until_the_deadline_report_blocked(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """State changes that never bring the target report blocked at the deadline,
        and each wait only lasts the time left before it."""
        mock_climate_data_reader.wait_for_state_change = AsyncMock(return_value=True)
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander,
            climate_data_reader=mock_climate_data_reader,
            action_effect_timeout_seconds=10.0,
        )

        with patch(f"{_USE_CASE_MODULE}.monotonic", side_effect=[0.0, 0.0, 4.0, 10.0]):
            result = await use_case.start_preheating(
                datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
            )

        assert result is False
        waits = [
            call.args[0] for call in mock_climate_data_reader.wait_for_state_change.await_args_list
        ]
        assert waits == [10.0, 6.0]

    @pytest.mark.asyncio
    async def test_unreadable_after_a_state_change_is_success(
        self, mock_scheduler_commander: Mock, mock_climate_data_reader: Mock
    ) -> None:
        """A VTherm becoming unavailable during the wait cannot prove the block (#64)."""

        async def _becomes_unavailable(timeout_seconds: float) -> bool:
            mock_climate_data_reader.get_target_temperature.return_value = None
            return True

        mock_climate_data_reader.wait_for_state_change.side_effect = _becomes_unavailable
        use_case = ControlPreheatingUseCase(
            mock_scheduler_commander, climate_data_reader=mock_climate_data_reader
        )

        result = await use_case.start_preheating(
            datetime(2026, 11, 1, 9, 0, 0), 20.0, "switch.weekend"
        )

        assert result is True
