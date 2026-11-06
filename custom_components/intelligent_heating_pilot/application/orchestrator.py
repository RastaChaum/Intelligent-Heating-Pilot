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
        update_cache: UpdateCacheDataUseCase,
    ) -> None:
        """Initialize the orchestrator with use cases.

        Args:
            calculate_anticipation: Use case for calculating anticipation data
            control_preheating: Use case for controlling preheating
            schedule_anticipation_action: Use case for scheduling anticipation actions
            update_cache: Use case for updating cache
        """
        _LOGGER.debug("Initializing HeatingOrchestrator")
        self._calculate_anticipation = calculate_anticipation
        self._control_preheating = control_preheating
        self._schedule_anticipation_action = schedule_anticipation_action
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

    async def cancel_pending_anticipation(self) -> None:
        """Cancel the pending anticipation timer without touching the thermostat.

        Used on unload/reload: reverting an active preheat there would cause a
        setpoint flap, since the reloaded instance re-triggers it if still due.
        """
        _LOGGER.debug("Entering HeatingOrchestrator.cancel_pending_anticipation()")
        await self._schedule_anticipation_action.cancel_action()

    async def disable_preheating(self, scheduler_entity_id: str) -> None:
        """Disable preheating (cancel timer and active preheating).

        Args:
            scheduler_entity_id: Scheduler entity to cancel
        """
        _LOGGER.debug("Entering HeatingOrchestrator.disable_preheating()")

        # Delegate to schedule_anticipation_action to cancel timer
        await self._schedule_anticipation_action.cancel_action()

        # Cancel active preheating if any
        await self._control_preheating.cancel_preheating(scheduler_entity_id)

        _LOGGER.info("Preheating disabled")
        _LOGGER.debug("Exiting HeatingOrchestrator.disable_preheating()")

    async def reset_all_learning_data(self, device_id: str) -> None:
        """Reset all learned data (LHS + cycles + dead time), in storage and memory.

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

    async def calculate_and_schedule_anticipation(self, ihp_enabled: bool = True) -> dict[str, Any]:
        """Calculate anticipation and handle scheduling based on IHP status.

        This orchestrator method:
        1. Calculates anticipation data
        2. Delegates scheduling decisions to ScheduleAnticipationActionUseCase
        3. Retries with the next candidate scheduler if the first one is confirmed
           blocked (its own conditions unmet), instead of waiting for its slot to
           naturally elapse (#64)
        4. Always returns anticipation data structure

        Args:
            ihp_enabled: Whether IHP preheating is enabled

        Returns:
            Dict with anticipation data for sensors (always returns structure).
            Includes ``scheduler_blocked`` (bool) and ``blocked_schedulers``
            (list[str]) reporting whether every configured scheduler was
            confirmed blocked this cycle.
        """
        return await self._run_anticipation_cycle(ihp_enabled, frozenset())

    async def retry_anticipation_after_blocked_scheduler(self, blocked_entity_id: str) -> None:
        """Re-enter the anticipation cycle, excluding a scheduler just confirmed blocked.

        Called by ScheduleAnticipationActionUseCase's ``on_scheduler_blocked``
        callback when a *timer-fired* trigger is confirmed blocked — that path
        fires outside any caller's awaited call stack, so it cannot propagate
        the blocked id through a return value the way the immediate-trigger
        path does. Not part of the integration-facing API.

        Args:
            blocked_entity_id: Scheduler entity id confirmed blocked.
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator.retry_anticipation_after_blocked_scheduler(%s)",
            blocked_entity_id,
        )
        await self._run_anticipation_cycle(True, frozenset({blocked_entity_id}))

    async def _run_anticipation_cycle(
        self, ihp_enabled: bool, seed_excluded: frozenset[str]
    ) -> dict[str, Any]:
        """Run one calculate-then-schedule cycle, retrying past confirmed-blocked schedulers.

        Args:
            ihp_enabled: Whether IHP preheating is enabled
            seed_excluded: Scheduler entity ids to exclude from the first attempt
                of this cycle (empty for a normal cycle; seeded with one entity
                when re-entering after a timer-fired block)

        Returns:
            The final anticipation data, annotated with ``scheduler_blocked``
            and ``blocked_schedulers``.
        """
        _LOGGER.debug(
            "Entering HeatingOrchestrator._run_anticipation_cycle(ihp_enabled=%s, seed_excluded=%s)",
            ihp_enabled,
            seed_excluded,
        )

        excluded = seed_excluded
        blocked: list[str] = list(seed_excluded)

        while True:
            # Step 1: Always calculate anticipation data regardless of IHP state.
            # The switch only controls whether preheating is scheduled, not whether
            # calculations happen. This ensures sensors and LHS caches stay up-to-date.
            anticipation_data = await self._calculate_anticipation.calculate_anticipation_datas(
                exclude_entity_ids=excluded
            )

            # Step 2: Delegate scheduling decisions to use case (respects ihp_enabled)
            blocked_entity = (
                await self._schedule_anticipation_action.handle_anticipation_scheduling(
                    anticipation_data,
                    ihp_enabled,
                )
            )

            if blocked_entity is None:
                break
            _LOGGER.info(
                "Scheduler %s confirmed blocked, retrying with the next candidate",
                blocked_entity,
            )
            blocked.append(blocked_entity)
            excluded = excluded | {blocked_entity}
            if anticipation_data.get("scheduler_entity") is None:
                break  # no candidate was even attempted this iteration; nothing to retry

        anticipation_data["scheduler_blocked"] = bool(blocked) and (
            anticipation_data.get("anticipated_start_time") is None
        )
        anticipation_data["blocked_schedulers"] = blocked
        if anticipation_data["scheduler_blocked"]:
            _LOGGER.warning("All configured schedulers are blocked this cycle: %s", blocked)

        _LOGGER.debug("Exiting HeatingOrchestrator._run_anticipation_cycle() -> data")
        return anticipation_data
