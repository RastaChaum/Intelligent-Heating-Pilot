"""Control Preheating Use Case.

This use case controls the preheating state (start/stop/clear).

STEP 1 IMPLEMENTATION: This is a facade/wrapper that delegates to
HeatingApplicationService internal methods for preheating control.
No behavior change - pure delegation pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from .. import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class ControlPreheatingUseCase:
    """Use case for controlling preheating state.

    This use case encapsulates operations for:
    1. Starting preheating
    2. Stopping preheating
    3. Clearing preheating state

    STEP 1: Delegates to HeatingApplicationService (no logic here yet).
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the use case.

        Args:
            application_service: The application service to delegate to
        """
        _LOGGER.debug("Initializing ControlPreheatingUseCase")
        self._app_service = application_service

    async def clear_anticipation_state(self) -> None:
        """Clear anticipation state (cancel timer, reset tracking).

        STEP 1: Delegates to _clear_anticipation_state().
        """
        _LOGGER.debug("Entering ControlPreheatingUseCase.clear_anticipation_state()")

        # STEP 1: Delegate to existing application service method
        await self._app_service._clear_anticipation_state()

        _LOGGER.debug("Exiting ControlPreheatingUseCase.clear_anticipation_state()")

    async def trigger_anticipation_action(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> None:
        """Trigger the anticipation action (run scheduler action).

        Args:
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger

        STEP 1: Delegates to _trigger_anticipation_action().
        """
        _LOGGER.debug(
            "Entering ControlPreheatingUseCase.trigger_anticipation_action(target_time=%s, temp=%.1f, scheduler=%s)",
            target_time.isoformat(),
            target_temp,
            scheduler_entity_id,
        )

        # STEP 1: Delegate to existing application service method
        await self._app_service._trigger_anticipation_action(
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
        )

        _LOGGER.debug("Exiting ControlPreheatingUseCase.trigger_anticipation_action()")

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        Returns:
            True if preheating is active, False otherwise

        STEP 1: Delegates to application service state.
        """
        _LOGGER.debug("ControlPreheatingUseCase.is_preheating_active()")
        return self._app_service._is_preheating_active

    def get_preheating_target_time(self) -> datetime | None:
        """Get the target time for active preheating.

        Returns:
            Target time if preheating is active, None otherwise

        STEP 1: Delegates to application service state.
        """
        _LOGGER.debug("ControlPreheatingUseCase.get_preheating_target_time()")
        return self._app_service._preheating_target_time
