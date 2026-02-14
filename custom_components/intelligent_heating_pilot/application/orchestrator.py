"""Heating Orchestrator.

The orchestrator composes use cases to implement complex workflows.
It coordinates multiple use cases but contains NO business logic itself.

STEP 1 IMPLEMENTATION: The orchestrator delegates to HeatingApplicationService
methods through use cases. This is a pure composition layer with no logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .use_cases import (
    CalculateAnticipationUseCase,
    ControlPreheatingUseCase,
    ResetLearningUseCase,
    ScheduleAnticipationActionUseCase,
    UpdateCacheDataUseCase,
)

if TYPE_CHECKING:
    from . import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class HeatingOrchestrator:
    """Orchestrates heating use cases.

    The orchestrator is responsible for:
    1. Composing use cases to implement workflows
    2. Coordinating the execution order of use cases
    3. Managing cross-use-case dependencies

    NO business logic - pure composition and coordination.

    STEP 1: Use cases delegate to HeatingApplicationService.
    STEP 3: Use cases will contain business logic, orchestrator will compose them.
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the orchestrator with use cases.

        Args:
            application_service: The application service (will be replaced
                                by individual adapters in later steps)
        """
        _LOGGER.debug("Initializing HeatingOrchestrator")

        # STEP 1: Create use cases that delegate to application service
        self._calculate_anticipation = CalculateAnticipationUseCase(application_service)
        self._control_preheating = ControlPreheatingUseCase(application_service)
        self._schedule_action = ScheduleAnticipationActionUseCase(application_service)
        self._update_cache = UpdateCacheDataUseCase(application_service)
        self._reset_learning = ResetLearningUseCase(application_service)

        # Store reference for direct access in STEP 1 (will be removed in STEP 3)
        self._app_service = application_service

    async def calculate_and_schedule_anticipation(
        self, ihp_enabled: bool = True
    ) -> dict | None:
        """Calculate anticipation and schedule preheating.

        STEP 1: Delegates to CalculateAnticipationUseCase.

        Args:
            ihp_enabled: Whether IHP preheating is enabled

        Returns:
            Dict with anticipation data for sensors, or None if not applicable
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator.calculate_and_schedule_anticipation(ihp_enabled=%s)",
            ihp_enabled,
        )

        # STEP 1: Direct delegation to use case
        result = await self._calculate_anticipation.execute(ihp_enabled=ihp_enabled)

        _LOGGER.debug(
            "Exiting HeatingOrchestrator.calculate_and_schedule_anticipation() -> %s",
            "data" if result else "None",
        )
        return result

    async def reset_learned_slopes(self) -> None:
        """Reset all learned heating slopes.

        STEP 1: Delegates to ResetLearningUseCase.
        """
        _LOGGER.debug("Entering HeatingOrchestrator.reset_learned_slopes()")

        # STEP 1: Direct delegation to use case
        await self._reset_learning.execute()

        _LOGGER.debug("Exiting HeatingOrchestrator.reset_learned_slopes()")

    async def clear_anticipation_state(self) -> None:
        """Clear anticipation state.

        STEP 1: Delegates to ControlPreheatingUseCase.
        """
        _LOGGER.debug("Entering HeatingOrchestrator.clear_anticipation_state()")

        # STEP 1: Direct delegation to use case
        await self._control_preheating.clear_anticipation_state()

        _LOGGER.debug("Exiting HeatingOrchestrator.clear_anticipation_state()")

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        STEP 1: Delegates to ControlPreheatingUseCase.

        Returns:
            True if preheating is active, False otherwise
        """
        return self._control_preheating.is_preheating_active()

    # STEP 1: Provide access to application service for backward compatibility
    # This will be removed in STEP 3 when logic is migrated to use cases
    @property
    def application_service(self) -> HeatingApplicationService:
        """Get the underlying application service.

        TEMPORARY: For backward compatibility during STEP 1.
        Will be removed in STEP 3.
        """
        return self._app_service
