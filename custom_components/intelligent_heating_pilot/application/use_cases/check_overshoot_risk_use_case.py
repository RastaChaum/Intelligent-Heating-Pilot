"""Check Overshoot Risk Use Case.

This use case detects when heating will overshoot the target temperature
and cancels preheating to avoid overheating.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.interfaces import (
        IClimateDataReader,
        IEnvironmentReader,
        ISchedulerReader,
    )
    from .control_preheating_use_case import ControlPreheatingUseCase

_LOGGER = logging.getLogger(__name__)


class CheckOvershootRiskUseCase:
    """Use case for detecting overshoot risk.

    This use case encapsulates the logic for:
    1. Reading current environment and slope
    2. Estimating temperature at target time
    3. Canceling preheating if overshoot risk is detected
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        environment_reader: IEnvironmentReader,
        climate_data_reader: IClimateDataReader,
        control_preheating: ControlPreheatingUseCase,
        overshoot_threshold_celsius: float = 0.5,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduled timeslots
            environment_reader: Reads current environment conditions
            climate_data_reader: Reads current heating slope
            control_preheating: Cancels preheating when risk detected
            overshoot_threshold_celsius: Temperature margin above target to consider as overshoot (°C)
        """
        _LOGGER.debug(
            "Initializing CheckOvershootRiskUseCase with threshold %.1f°C",
            overshoot_threshold_celsius,
        )
        self._scheduler_reader = scheduler_reader
        self._environment_reader = environment_reader
        self._climate_data_reader = climate_data_reader
        self._control_preheating = control_preheating
        self._overshoot_threshold = overshoot_threshold_celsius

    async def check_and_prevent_overshoot(self, scheduler_entity_id: str) -> bool:
        """Check for overshoot risk and cancel preheating if needed.

        Args:
            scheduler_entity_id: Scheduler entity tied to preheating

        Returns:
            True if overshoot detected and preheating canceled, False otherwise
        """
        _LOGGER.debug(
            "Entering CheckOvershootRiskUseCase.check_and_prevent_overshoot(scheduler=%s)",
            scheduler_entity_id,
        )

        if not self._control_preheating.is_preheating_active():
            _LOGGER.debug("Skipping overshoot check - preheating not active")
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
            return False

        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            _LOGGER.debug("Skipping overshoot check - no timeslot available")
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
            return False

        environment = await self._environment_reader.get_current_environment()
        if not environment:
            # Safety first: If we can't read temperature, assume overshoot risk
            _LOGGER.warning("No environment data available - assuming overshoot risk for safety")
            await self._control_preheating.cancel_preheating(scheduler_entity_id)
            _LOGGER.info("Cancelled preheating due to missing environment data")
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> True")
            return True

        current_slope = self._climate_data_reader.get_current_slope()
        if current_slope is None or current_slope <= 0.0:
            # Cannot check overshoot without valid slope data
            _LOGGER.debug(
                "Current slope unavailable (%.2f°C/h) - skipping overshoot check",
                current_slope or 0.0,
            )
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
            return False

        now = environment.timestamp
        if now >= timeslot.target_time:
            _LOGGER.debug("Skipping overshoot check - target time already passed")
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
            return False

        time_to_target_hours = (timeslot.target_time - now).total_seconds() / 3600.0
        projected_temp = environment.indoor_temperature + (current_slope * time_to_target_hours)
        overshoot_limit = timeslot.target_temp + self._overshoot_threshold

        _LOGGER.debug(
            "Overshoot check: current=%.1f°C projected=%.1f°C target=%.1f°C limit=%.1f°C",
            environment.indoor_temperature,
            projected_temp,
            timeslot.target_temp,
            overshoot_limit,
        )

        if projected_temp >= overshoot_limit:
            _LOGGER.warning(
                "Overshoot risk detected: projected %.1f°C exceeds limit %.1f°C",
                projected_temp,
                overshoot_limit,
            )
            await self._control_preheating.cancel_preheating(scheduler_entity_id)
            _LOGGER.debug("Exiting check_and_prevent_overshoot() -> True")
            return True

        _LOGGER.debug("No overshoot risk detected")
        _LOGGER.debug("Exiting check_and_prevent_overshoot() -> False")
        return False
