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
    CheckOvershootRiskUseCase,
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
    UpdateCacheDataUseCase,
)

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Any

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
        schedule_anticipation_action: ScheduleAnticipationActionUseCase,
        check_overshoot_risk: CheckOvershootRiskUseCase,
        update_cache: UpdateCacheDataUseCase,
    ) -> None:
        """Initialize the orchestrator with use cases.

        Args:
            calculate_anticipation: Use case for calculating anticipation data
            control_preheating: Use case for controlling preheating
            schedule_anticipation_action: Use case for scheduling anticipation actions
            check_overshoot_risk: Use case for checking overshoot risk
            update_cache: Use case for updating cache
        """
        _LOGGER.debug("Initializing HeatingOrchestrator")
        self._calculate_anticipation = calculate_anticipation
        self._control_preheating = control_preheating
        self._schedule_anticipation_action = schedule_anticipation_action
        self._check_overshoot_risk = check_overshoot_risk
        self._update_cache = update_cache

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

    async def disable_preheating(self, scheduler_entity_id: str) -> None:
        """Disable preheating (cancel timer and active preheating).

        Args:
            scheduler_entity_id: Scheduler entity to cancel
        """
        _LOGGER.debug("Entering HeatingOrchestrator.disable_preheating()")

        # Delegate to schedule_anticipation_action to cancel timer
        await self._schedule_anticipation_action.cancel_action()

        # Cancel active preheating if any
        if self._control_preheating.is_preheating_active():
            await self._control_preheating.cancel_preheating(scheduler_entity_id)

        _LOGGER.info("Preheating disabled")
        _LOGGER.debug("Exiting HeatingOrchestrator.disable_preheating()")

    async def reset_all_learning_data(self, device_id: str) -> None:
        """Reset all learned data (LHS + cycles).

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug("Entering HeatingOrchestrator.reset_all_learning_data()")

        await self._update_cache.reset_cache(device_id)

        _LOGGER.debug("Exiting HeatingOrchestrator.reset_all_learning_data()")

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        Returns:
            True if preheating is active, False otherwise
        """
        return self._control_preheating.is_preheating_active()

    async def calculate_and_schedule_anticipation(
        self, ihp_enabled: bool = True
    ) -> dict[str, Any]:
        """Calculate anticipation and optionally schedule preheating.

        This method:
        1. Calculates anticipation data using CalculateAnticipationUseCase
        2. If valid data and IHP enabled, schedules preheating
        3. If valid data and IHP disabled, ensures preheating is cancelled
        4. Always returns anticipation data structure (with None values if needed)

        Args:
            ihp_enabled: Whether IHP preheating is enabled. When False,
                        cancels any active preheating but continues calculations.

        Returns:
            Dict with anticipation data for sensors (always returns structure)
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator.calculate_and_schedule_anticipation(ihp_enabled=%s)",
            ihp_enabled,
        )

        # Step 1: Calculate anticipation data
        anticipation_data = await self._calculate_anticipation.calculate_anticipation_datas()

        # Step 2: Handle scheduling based on data availability and IHP status
        if anticipation_data.get("anticipated_start_time") is None:
            # No valid data - cancel any active scheduling
            _LOGGER.debug("No valid anticipation data - cancelling any active scheduling")
            await self._schedule_anticipation_action.cancel_action()
            if self._control_preheating.is_preheating_active():
                scheduler_entity = self._control_preheating.get_active_scheduler_entity()
                if scheduler_entity:
                    await self._control_preheating.cancel_preheating(scheduler_entity)
            _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> data with None values")
            return anticipation_data

        if not ihp_enabled:
            # IHP disabled - cancel but return data
            _LOGGER.debug("IHP disabled - cancelling preheating if active")
            if self._control_preheating.is_preheating_active():
                scheduler_entity = (
                    self._control_preheating.get_active_scheduler_entity()
                    or anticipation_data.get("scheduler_entity")
                )
                if scheduler_entity:
                    await self._control_preheating.cancel_preheating(scheduler_entity)
            await self._schedule_anticipation_action.cancel_action()
            _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> data")
            return anticipation_data

        if anticipation_data.get("anticipation_minutes") == 0:
            # Target reached - clear state
            _LOGGER.debug("Target reached - clearing anticipation state")
            await self._schedule_anticipation_action.cancel_action()
            if self._control_preheating.is_preheating_active():
                scheduler_entity = (
                    self._control_preheating.get_active_scheduler_entity()
                    or anticipation_data.get("scheduler_entity")
                )
                if scheduler_entity:
                    await self._control_preheating.cancel_preheating(scheduler_entity)
            _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> data")
            return anticipation_data

        # Step 3: Schedule preheating action
        scheduler_entity = anticipation_data.get("scheduler_entity")
        if not scheduler_entity:
            _LOGGER.debug("No scheduler entity - skipping scheduling")
            _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> data")
            return anticipation_data

        await self._schedule_anticipation_action.schedule_action(
            anticipated_start=anticipation_data["anticipated_start_time"],
            target_time=anticipation_data["next_schedule_time"],
            target_temp=anticipation_data["next_target_temperature"],
            scheduler_entity_id=scheduler_entity,
            lhs=float(anticipation_data.get("learned_heating_slope") or 0.0),
        )

        _LOGGER.debug("Exiting HeatingOrchestrator.calculate_and_schedule_anticipation() -> data")
        return anticipation_data

    async def check_and_prevent_overshoot(self, scheduler_entity_id: str) -> bool:
        """Check overshoot risk and cancel preheating if needed.

        Args:
            scheduler_entity_id: Scheduler entity to cancel if overshoot detected

        Returns:
            True if overshoot detected and cancellation triggered, False otherwise
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator.check_and_prevent_overshoot(scheduler=%s)",
            scheduler_entity_id,
        )

        if not self._control_preheating.is_preheating_active():
            _LOGGER.debug("No active preheating - skipping overshoot check")
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
            return False

        overshoot_detected = await self._check_overshoot_risk.check_and_prevent_overshoot(
            scheduler_entity_id=scheduler_entity_id
        )

        if overshoot_detected:
            await self._schedule_anticipation_action.cancel_action()

        _LOGGER.debug(
            "Exiting HeatingOrchestrator.check_and_prevent_overshoot() -> %s",
            overshoot_detected,
        )
        return overshoot_detected
