"""Calculate Anticipation Data Use Case.

This use case calculates the anticipated start time for preheating
based on current conditions and learned heating slopes.

This is a PURE CALCULATION use case - it does NOT schedule or trigger preheating.
For scheduling, use SchedulePreheatingUseCase.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import IEnvironmentReader, ISchedulerReader
    from ...domain.services import DeadTimeCalculationService, PredictionService
    from ..heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager
    from ..lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)


class CalculateAnticipationUseCase:
    """Use case for calculating anticipation data (NO preheating scheduling).

    This use case encapsulates the pure calculation logic for:
    1. Reading the next scheduled timeslot
    2. Getting heating cycles for LHS calculation
    3. Calculating the anticipated start time based on learned heating slope
    4. Returning anticipation data for display/sensors

    This does NOT schedule or trigger any preheating action.
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        environment_reader: IEnvironmentReader,
        heating_cycle_manager: HeatingCycleLifecycleManager,
        lhs_lifecycle_manager: LhsLifecycleManager,
        prediction_service: PredictionService,
        dead_time_calculator: DeadTimeCalculationService,
        auto_learning: bool = True,
        default_dead_time_minutes: float = 0.0,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduled timeslots
            environment_reader: Reads current environment conditions
            heating_cycle_manager: Manages heating cycle lifecycle
            lhs_lifecycle_manager: Manages learned heating slopes
            prediction_service: Predicts heating time
            dead_time_calculator: Calculates dead time from cycles
            auto_learning: Whether auto-learning is enabled
            default_dead_time_minutes: Default dead time when not learned
        """
        _LOGGER.debug("Initializing CalculateAnticipationUseCase")
        self._scheduler_reader = scheduler_reader
        self._environment_reader = environment_reader
        self._heating_cycle_manager = heating_cycle_manager
        self._lhs_manager = lhs_lifecycle_manager
        self._prediction_service = prediction_service
        self._dead_time_calculator = dead_time_calculator
        self._auto_learning = auto_learning
        self._default_dead_time_minutes = default_dead_time_minutes

    async def calculate_anticipation_datas(
        self,
        target_time: datetime | None = None,
    ) -> dict:
        """Calculate anticipation data without scheduling preheating.

        Args:
            target_time: Optional target time. If None, uses next scheduled timeslot.

        Returns:
            Dict with anticipation data. Returns structure with None values if
            no scheduler configured or no valid timeslot available.
            Structure:
            {
                "anticipated_start_time": datetime | None,
                "next_schedule_time": datetime | None,
                "next_target_temperature": float | None,
                "anticipation_minutes": float | None,
                "current_temp": float | None,
                "learned_heating_slope": float | None,
                "confidence_level": float | None,
                "timeslot_id": str | None,
                "scheduler_entity": str | None,
            }
        """
        _LOGGER.debug(
            "Entering CalculateAnticipationUseCase.calculate_anticipation_datas(target_time=%s)",
            target_time.isoformat() if target_time else "None",
        )

        # Get timeslot (either provided target_time or next scheduled)
        if target_time is None:
            timeslot = await self._scheduler_reader.get_next_timeslot()
            if not timeslot:
                _LOGGER.debug("No scheduled timeslot found")
                return self._empty_data_structure()
        else:
            # Use provided target_time to find matching timeslot
            timeslot = await self._scheduler_reader.get_next_timeslot()
            if not timeslot:
                _LOGGER.debug("No scheduler configured")
                return self._empty_data_structure()

        # Get current environment
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            _LOGGER.warning("Cannot read current environment")
            return self._empty_data_structure()

        # Get device ID
        vtherm_id = self._environment_reader.get_vtherm_entity_id()

        # Get heating cycles for LHS calculation
        heating_cycles = await self._heating_cycle_manager.get_cycles_for_target_time(
            device_id=vtherm_id,
            target_time=timeslot.target_time,
        )

        # Get contextual LHS
        lhs = await self._lhs_manager.get_contextual_lhs(
            target_time=timeslot.target_time,
            cycles=heating_cycles,
        )

        # Calculate effective dead_time
        if self._auto_learning and heating_cycles:
            avg_dead_time = self._dead_time_calculator.calculate_average_dead_time(heating_cycles)
            if avg_dead_time is not None and avg_dead_time > 0:
                dead_time = avg_dead_time
                _LOGGER.info(
                    "Learned dead_time from %d cycles: %.1f minutes",
                    len(heating_cycles),
                    dead_time,
                )
            else:
                dead_time = self._default_dead_time_minutes
        else:
            dead_time = self._default_dead_time_minutes

        # Check if already at target
        if environment.indoor_temperature >= timeslot.target_temp:
            _LOGGER.debug(
                "Already at target (%.1f°C >= %.1f°C)",
                environment.indoor_temperature,
                timeslot.target_temp,
            )
            result = {
                "anticipated_start_time": timeslot.target_time,
                "next_schedule_time": timeslot.target_time,
                "next_target_temperature": timeslot.target_temp,
                "anticipation_minutes": 0.0,
                "current_temp": environment.indoor_temperature,
                "learned_heating_slope": lhs,
                "confidence_level": 100.0,
                "timeslot_id": timeslot.timeslot_id,
                "scheduler_entity": timeslot.scheduler_entity,
            }
            _LOGGER.debug("Exiting calculate_anticipation_datas() -> already at target")
            return result

        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.indoor_temperature,
            target_temp=timeslot.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.indoor_humidity,
            learned_slope=lhs,
            target_time=timeslot.target_time,
            cloud_coverage=environment.cloud_coverage,
            dead_time_minutes=dead_time,
        )

        _LOGGER.info(
            "Calculated anticipation: start at %s (%.1f min) for target %.1f°C at %s (LHS: %.2f°C/h)",
            prediction.anticipated_start_time.isoformat(),
            prediction.estimated_duration_minutes,
            timeslot.target_temp,
            timeslot.target_time.isoformat(),
            prediction.learned_heating_slope,
        )

        result = {
            "anticipated_start_time": prediction.anticipated_start_time,
            "next_schedule_time": timeslot.target_time,
            "next_target_temperature": timeslot.target_temp,
            "anticipation_minutes": prediction.estimated_duration_minutes,
            "current_temp": environment.indoor_temperature,
            "learned_heating_slope": prediction.learned_heating_slope,
            "confidence_level": prediction.confidence_level,
            "timeslot_id": timeslot.timeslot_id,
            "scheduler_entity": timeslot.scheduler_entity,
        }

        _LOGGER.debug("Exiting calculate_anticipation_datas() -> %s", "data")
        return result

    def _empty_data_structure(self) -> dict:
        """Return empty data structure with all fields set to None.

        Returns consistent structure even when no data is available.
        """
        return {
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "anticipation_minutes": None,
            "current_temp": None,
            "learned_heating_slope": None,
            "confidence_level": None,
            "timeslot_id": None,
            "scheduler_entity": None,
        }
