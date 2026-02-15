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
    from ..domain.interfaces import (
        IClimateCommander,
        IEnvironmentReader,
        IHeatingCycleStorage,
        ILhsStorage,
        ISchedulerCommander,
        ISchedulerReader,
        ITimerScheduler,
    )
    from ..domain.services import PredictionService
    from .lhs_lifecycle_manager import LhsLifecycleManager

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
        scheduler_reader: ISchedulerReader,
        scheduler_commander: ISchedulerCommander,
        climate_commander: IClimateCommander,
        environment_reader: IEnvironmentReader,
        timer_scheduler: ITimerScheduler,
        lhs_storage: ILhsStorage,
        cycle_cache: IHeatingCycleStorage,
        lhs_lifecycle_manager: LhsLifecycleManager,
        prediction_service: PredictionService,
    ) -> None:
        """Initialize the orchestrator with use cases.

        Args:
            scheduler_reader: Reads scheduled timeslots
            scheduler_commander: Commands scheduler actions
            climate_commander: Commands climate entity
            environment_reader: Reads environment conditions
            timer_scheduler: Schedules timer callbacks
            lhs_storage: Storage for learned heating slopes
            cycle_cache: Storage for heating cycles cache
            lhs_lifecycle_manager: Manages LHS lifecycle
            prediction_service: Predicts heating time
        """
        _LOGGER.debug("Initializing HeatingOrchestrator")

        # Create use cases
        self._calculate_anticipation = CalculateAnticipationUseCase(
            scheduler_reader=scheduler_reader,
            environment_reader=environment_reader,
            lhs_lifecycle_manager=lhs_lifecycle_manager,
            prediction_service=prediction_service,
        )
        self._control_preheating = ControlPreheatingUseCase(
            scheduler_commander=scheduler_commander,
            climate_commander=climate_commander,
        )
        self._schedule_preheating = SchedulePreheatingUseCase(
            timer_scheduler=timer_scheduler,
        )
        self._update_cache = UpdateCacheDataUseCase(
            cycle_cache=cycle_cache,
        )
        self._reset_learning = ResetLearningUseCase(
            lhs_storage=lhs_storage,
            cycle_cache=cycle_cache,
        )

    async def calculate_and_schedule_anticipation(
        self, ihp_enabled: bool = True
    ) -> dict:
        """Calculate anticipation and optionally schedule preheating.

        This is the main workflow that:
        1. Calculates anticipation data
        2. If IHP enabled, schedules preheating timer
        3. Returns data for sensors

        Args:
            ihp_enabled: Whether IHP preheating is enabled

        Returns:
            Dict with anticipation data (may contain None values if no data)
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator.calculate_and_schedule_anticipation(ihp_enabled=%s)",
            ihp_enabled,
        )

        # Step 1: Calculate anticipation data (pure calculation, no scheduling)
        anticipation_data = await self._calculate_anticipation.calculate_anticipation_datas()

        # Check if we have valid data
        if anticipation_data["anticipated_start_time"] is None:
            _LOGGER.debug("No valid anticipation data - skipping scheduling")
            _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> no data")
            return anticipation_data

        # Step 2: Schedule preheating if IHP is enabled
        if ihp_enabled:
            # Create callback for timer
            async def preheating_callback() -> None:
                """Callback to trigger preheating when timer fires."""
                await self._control_preheating.start_preheating(
                    target_time=anticipation_data["next_schedule_time"],
                    target_temp=anticipation_data["next_target_temperature"],
                    scheduler_entity_id=anticipation_data["scheduler_entity"],
                )

            # Schedule the timer
            await self._schedule_preheating.schedule_preheating(
                anticipated_start=anticipation_data["anticipated_start_time"],
                preheating_callback=preheating_callback,
            )
            _LOGGER.info(
                "Preheating scheduled for %s",
                anticipation_data["anticipated_start_time"].isoformat(),
            )
        else:
            # IHP disabled - cancel any active preheating
            if self._control_preheating.is_preheating_active():
                scheduler_entity = self._control_preheating.get_active_scheduler_entity()
                if scheduler_entity:
                    await self._control_preheating.cancel_preheating(scheduler_entity)
            _LOGGER.debug("IHP disabled - preheating not scheduled")

        _LOGGER.debug("Exiting calculate_and_schedule_anticipation() -> data")
        return anticipation_data

    async def cancel_preheating(self, scheduler_entity_id: str) -> None:
        """Cancel active preheating.

        Args:
            scheduler_entity_id: Scheduler entity to cancel
        """
        _LOGGER.debug("Entering HeatingOrchestrator.cancel_preheating()")

        # Cancel timer
        await self._schedule_preheating.cancel_preheating_timer()

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

    async def update_cache(
        self,
        device_id: str,
        cycles: list,
        search_end_time,
    ) -> None:
        """Update cache with new cycles.

        Args:
            device_id: Device identifier
            cycles: New cycles to append
            search_end_time: End time of search
        """
        await self._update_cache.append_cycles(device_id, cycles, search_end_time)

    async def prune_cache(self, device_id: str, reference_time) -> None:
        """Prune old cycles from cache.

        Args:
            device_id: Device identifier
            reference_time: Reference time for pruning
        """
        await self._update_cache.prune_old_cycles(device_id, reference_time)
