"""Control Preheating Use Case.

This use case controls the preheating state (start/cancel).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import ISchedulerCommander

_LOGGER = logging.getLogger(__name__)


class ControlPreheatingUseCase:
    """Use case for controlling preheating state.

    This use case encapsulates operations for:
    1. Starting preheating (trigger scheduler action)
    2. Canceling preheating (revert to current scheduled state)
    3. Tracking preheating state
    """

    def __init__(
        self,
        scheduler_commander: ISchedulerCommander,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_commander: Commands scheduler actions
        """
        _LOGGER.debug("Initializing ControlPreheatingUseCase")
        self._scheduler_commander = scheduler_commander
        self._is_preheating_active = False
        self._preheating_target_time: datetime | None = None
        self._active_scheduler_entity: str | None = None

    async def cancel_preheating(self, scheduler_entity_id: str) -> None:
        """Cancel active preheating and revert to current scheduled state.

        Args:
            scheduler_entity_id: Scheduler entity to cancel action on
        """
        _LOGGER.debug(
            "Entering ControlPreheatingUseCase.cancel_preheating(scheduler=%s)",
            scheduler_entity_id,
        )

        if self._is_preheating_active:
            _LOGGER.info(
                "Canceling preheating for scheduler %s - reverting to current scheduled state",
                scheduler_entity_id,
            )
            # Call cancel_action to revert thermostat to current time's preset/temperature
            await self._scheduler_commander.cancel_action(scheduler_entity_id)
        else:
            _LOGGER.debug("No active preheating to cancel")

        # Clear state
        self._is_preheating_active = False
        self._preheating_target_time = None
        self._active_scheduler_entity = None

        _LOGGER.debug("Exiting ControlPreheatingUseCase.cancel_preheating()")

    async def start_preheating(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> None:
        """Start preheating by triggering scheduler action.

        Args:
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
        """
        _LOGGER.debug(
            "Entering ControlPreheatingUseCase.start_preheating(target_time=%s, temp=%.1f, scheduler=%s)",
            target_time.isoformat(),
            target_temp,
            scheduler_entity_id,
        )
        _LOGGER.info(
            "Starting preheating for target %s (%.1f°C)",
            target_time.isoformat(),
            target_temp,
        )

        # Use scheduler's run_action to trigger the action
        await self._scheduler_commander.run_action(target_time, scheduler_entity_id)

        # Mark pre-heating as active
        self._is_preheating_active = True
        self._preheating_target_time = target_time
        self._active_scheduler_entity = scheduler_entity_id

        _LOGGER.debug("Exiting ControlPreheatingUseCase.start_preheating()")

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        Returns:
            True if preheating is active, False otherwise
        """
        return self._is_preheating_active

    def get_preheating_target_time(self) -> datetime | None:
        """Get the target time for active preheating.

        Returns:
            Target time if preheating is active, None otherwise
        """
        return self._preheating_target_time

    def get_active_scheduler_entity(self) -> str | None:
        """Get the active scheduler entity.

        Returns:
            Scheduler entity ID if active, None otherwise
        """
        return self._active_scheduler_entity
