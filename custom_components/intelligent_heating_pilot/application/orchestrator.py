"""Heating Orchestrator.

The orchestrator composes use cases to implement complex workflows.
It coordinates multiple use cases but contains NO business logic itself.

This is the main entry point for heating operations from the infrastructure layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .use_cases import (
    CalculateAnticipationUseCase,
    ControlPreheatingUseCase,
    ResetLearningUseCase,
    SchedulePreheatingUseCase,
    UpdateCacheDataUseCase,
)

if TYPE_CHECKING:
    from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class HeatingOrchestrator:
    """Orchestrates heating use cases.

    The orchestrator is responsible for:
    1. Composing use cases to implement workflows
    2. Coordinating the execution order of use cases
    3. Managing cross-use-case dependencies

    NO business logic - pure composition and coordination.
    """

    def __init__(
        self,
        calculate_anticipation: CalculateAnticipationUseCase,
        control_preheating: ControlPreheatingUseCase,
        schedule_preheating: SchedulePreheatingUseCase,
        update_cache: UpdateCacheDataUseCase,
        reset_learning: ResetLearningUseCase,
    ) -> None:
        """Initialize the orchestrator with use cases.

        Args:
            calculate_anticipation: Use case for calculating anticipation data
            control_preheating: Use case for controlling preheating
            schedule_preheating: Use case for scheduling preheating timer
            update_cache: Use case for updating cache
            reset_learning: Use case for resetting learning data
        """
        _LOGGER.debug("Initializing HeatingOrchestrator")
        self._calculate_anticipation = calculate_anticipation
        self._control_preheating = control_preheating
        self._schedule_preheating = schedule_preheating
        self._update_cache = update_cache
        self._reset_learning = reset_learning

    async def calculate_anticipation_only(
        self,
        target_time: datetime | None = None,
        target_temp: float | None = None,
    ) -> dict:
        """Calculate anticipation data only (no scheduling).

        For users who use the service without a scheduler (via REST API).

        Args:
            target_time: Target time for heating
            target_temp: Target temperature

        Returns:
            Dict with anticipation data
        """
        _LOGGER.debug("Entering HeatingOrchestrator.calculate_anticipation_only()")

        result = await self._calculate_anticipation.calculate_anticipation_datas(
            target_time=target_time,
            target_temp=target_temp,
        )

        _LOGGER.debug("Exiting calculate_anticipation_only() -> data")
        return result

    async def enable_preheating(self) -> dict:
        """Calculate anticipation and enable preheating.

        This is the main workflow that:
        1. Calculates anticipation data
        2. Schedules preheating timer if data is valid
        3. Returns data for sensors

        Returns:
            Dict with anticipation data (may contain None values if no data)
        """
        _LOGGER.debug("Entering HeatingOrchestrator.enable_preheating()")

        # Step 1: Calculate anticipation data (pure calculation, no scheduling)
        anticipation_data = await self._calculate_anticipation.calculate_anticipation_datas()

        # Check if we have valid data
        if anticipation_data["anticipated_start_time"] is None:
            _LOGGER.debug("No valid anticipation data - skipping scheduling")
            _LOGGER.debug("Exiting enable_preheating() -> no data")
            return anticipation_data

        # Step 2: Schedule preheating timer
        # Create callback for timer
        async def preheating_callback() -> None:
            """Callback to trigger preheating when timer fires."""
            await self._control_preheating.start_preheating(
                target_time=anticipation_data["next_schedule_time"],
                target_temp=anticipation_data["next_target_temperature"],
                scheduler_entity_id=anticipation_data["scheduler_entity"],
            )

        # Schedule the timer
        await self._schedule_preheating.create_preheating_scheduler(
            anticipated_start=anticipation_data["anticipated_start_time"],
            preheating_callback=preheating_callback,
        )
        _LOGGER.info(
            "Preheating enabled and scheduled for %s",
            anticipation_data["anticipated_start_time"].isoformat(),
        )

        _LOGGER.debug("Exiting enable_preheating() -> data")
        return anticipation_data

    async def disable_preheating(self, scheduler_entity_id: str) -> None:
        """Disable preheating (cancel timer and active preheating).

        Args:
            scheduler_entity_id: Scheduler entity to cancel
        """
        _LOGGER.debug("Entering HeatingOrchestrator.disable_preheating()")

        # Cancel timer
        await self._schedule_preheating.cancel_preheating_scheduler()

        # Cancel active preheating if any
        if self._control_preheating.is_preheating_active():
            await self._control_preheating.cancel_preheating(scheduler_entity_id)

        _LOGGER.info("Preheating disabled")
        _LOGGER.debug("Exiting HeatingOrchestrator.disable_preheating()")

    async def cancel_preheating(self, scheduler_entity_id: str) -> None:
        """Cancel active preheating.

        Args:
            scheduler_entity_id: Scheduler entity to cancel
        """
        _LOGGER.debug("Entering HeatingOrchestrator.cancel_preheating()")

        # Cancel timer
        await self._schedule_preheating.cancel_preheating_scheduler()

        # Cancel preheating action
        await self._control_preheating.cancel_preheating(scheduler_entity_id)

        _LOGGER.debug("Exiting HeatingOrchestrator.cancel_preheating()")

    async def reset_all_learning_data(self, device_id: str) -> None:
        """Reset all learned data (LHS + cycles).

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug("Entering HeatingOrchestrator.reset_all_learning_data()")

        await self._reset_learning.reset_all_learning_data(device_id)

        _LOGGER.debug("Exiting HeatingOrchestrator.reset_all_learning_data()")

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        Returns:
            True if preheating is active, False otherwise
        """
        return self._control_preheating.is_preheating_active()
