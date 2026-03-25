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

    from ...domain.interfaces import (
        IClimateDataReader,
        IEnvironmentReader,
        ILhsStorage,
        ISchedulerReader,
    )
    from ...domain.services import DeadTimeCalculationService, PredictionService
    from ..heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager
    from ..lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)


class CalculateAnticipationUseCase:
    """Use case for calculating anticipation data (NO preheating scheduling).

    This use case encapsulates the pure calculation logic for:
    1. Reading the next scheduled timeslot (or using provided target_time)
    2. Getting heating cycles for LHS calculation
    3. Calculating the anticipated start time based on learned heating slope
    4. Returning anticipation data for display/sensors

    This does NOT schedule or trigger any preheating action.
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader | None,
        environment_reader: IEnvironmentReader,
        climate_data_reader: IClimateDataReader,
        heating_cycle_manager: HeatingCycleLifecycleManager,
        lhs_lifecycle_manager: LhsLifecycleManager,
        prediction_service: PredictionService,
        dead_time_calculator: DeadTimeCalculationService,
        auto_learning: bool = True,
        default_dead_time_minutes: float = 0.0,
        lhs_storage: ILhsStorage | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduled timeslots (optional for API-only usage)
            environment_reader: Reads current environment conditions
            climate_data_reader: Unified reader for VTherm metadata, slope and heating state
            heating_cycle_manager: Manages heating cycle lifecycle
            lhs_lifecycle_manager: Manages learned heating slopes
            prediction_service: Predicts heating time
            dead_time_calculator: Calculates dead time from cycles
            auto_learning: Whether auto-learning is enabled
            default_dead_time_minutes: Default dead time when not learned
            lhs_storage: Optional persistent storage for learned values. When provided
                and auto_learning is True, the stored learned dead time is used as a
                fallback before the configured default, so that the persisted value
                is restored immediately after a Home Assistant restart.
        """
        _LOGGER.debug("Initializing CalculateAnticipationUseCase")
        self._scheduler_reader = scheduler_reader
        self._environment_reader = environment_reader
        self._climate_data_reader = climate_data_reader
        self._heating_cycle_manager = heating_cycle_manager
        self._lhs_manager = lhs_lifecycle_manager
        self._prediction_service = prediction_service
        self._dead_time_calculator = dead_time_calculator
        self._auto_learning = auto_learning
        self._default_dead_time_minutes = default_dead_time_minutes
        self._lhs_storage = lhs_storage

    async def calculate_anticipation_datas(
        self,
        target_time: datetime | None = None,
        target_temp: float | None = None,
    ) -> dict:
        """Calculate anticipation data without scheduling preheating.

        Args:
            target_time: Target time for heating. If None, uses next scheduled timeslot.
            target_temp: Target temperature. If None, uses value from timeslot.

        Returns:
            Dict with anticipation data. Returns structure with None values for fields
            that cannot be calculated.
        """
        _LOGGER.debug(
            "Entering CalculateAnticipationUseCase.calculate_anticipation_datas(target_time=%s, target_temp=%s)",
            target_time.isoformat() if target_time else "None",
            target_temp,
        )

        # Import default constant for LHS validation
        from ...domain.constants import DEFAULT_LEARNED_SLOPE, MINIMUM_REALISTIC_LHS

        # Determine target time and temp
        timeslot = None
        scheduler_entity = None
        timeslot_id = None

        # Always get environment data (for minimal return structure)
        environment = await self._environment_reader.get_current_environment()
        current_temp = environment.indoor_temperature if environment else None

        # Always get global LHS (for minimal return structure)
        global_lhs = await self._lhs_manager.get_global_lhs()

        # Validate global LHS: must be realistically positive (>= 0.5°C/h)
        if global_lhs is None or global_lhs < MINIMUM_REALISTIC_LHS:
            _LOGGER.warning(
                "Invalid global LHS (%.4f°C/h < %.2f°C/h), using default (%.2f°C/h)",
                global_lhs or 0,
                MINIMUM_REALISTIC_LHS,
                DEFAULT_LEARNED_SLOPE,
            )
            global_lhs = DEFAULT_LEARNED_SLOPE

        if target_time is None:
            # Use scheduler to get next timeslot
            if self._scheduler_reader is None:
                _LOGGER.debug("No scheduler reader configured and no target_time provided")
                # Return minimal data structure
                return self._create_data_structure(
                    current_temp=current_temp,
                    learned_heating_slope=global_lhs,
                )

            timeslot = await self._scheduler_reader.get_next_timeslot()
            if not timeslot:
                _LOGGER.debug("No scheduled timeslot found")
                # Return minimal data structure
                return self._create_data_structure(
                    current_temp=current_temp,
                    learned_heating_slope=global_lhs,
                )

            target_time = timeslot.target_time
            target_temp = timeslot.target_temp
            scheduler_entity = timeslot.scheduler_entity
            timeslot_id = timeslot.timeslot_id
        else:
            # Using provided target_time (API/REST usage without scheduler)
            if target_temp is None:
                _LOGGER.warning("target_time provided but target_temp is None")
                # Return minimal data structure
                return self._create_data_structure(
                    current_temp=current_temp,
                    learned_heating_slope=global_lhs,
                )

        # Get remaining environment data
        outdoor_temp = environment.outdoor_temp if environment else None
        humidity = environment.indoor_humidity if environment else None
        cloud_coverage = environment.cloud_coverage if environment else None

        # Get device ID
        vtherm_id = self._climate_data_reader.get_vtherm_entity_id()

        # Get heating cycles for LHS calculation
        heating_cycles = await self._heating_cycle_manager.get_cycles_for_target_time(
            device_id=vtherm_id,
            target_time=target_time,
        )

        # Get contextual LHS
        lhs = await self._lhs_manager.get_contextual_lhs(
            target_time=target_time,
            cycles=heating_cycles,
        )

        # Validate LHS: must be realistically positive (>= 0.5°C/h)
        if lhs is None or lhs < MINIMUM_REALISTIC_LHS:
            _LOGGER.warning(
                "Invalid contextual LHS (%.4f°C/h < %.2f°C/h), using default (%.2f°C/h)",
                lhs or 0,
                MINIMUM_REALISTIC_LHS,
                DEFAULT_LEARNED_SLOPE,
            )
            lhs = DEFAULT_LEARNED_SLOPE

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
                dead_time = await self._get_persisted_dead_time_or_default()
        elif self._auto_learning:
            # No cycles available yet (e.g. immediately after restart before extraction).
            # Fall back to the persisted learned dead time so the correct value is used
            # before the first cycle extraction completes.
            dead_time = await self._get_persisted_dead_time_or_default()
        else:
            dead_time = self._default_dead_time_minutes

        # Calculate prediction - let prediction_service handle None values
        prediction = self._prediction_service.predict_heating_time(
            current_temp=current_temp,  # Pass None if unavailable
            target_temp=target_temp,
            outdoor_temp=outdoor_temp,
            humidity=humidity,
            learned_slope=lhs,
            target_time=target_time,
            cloud_coverage=cloud_coverage,
            dead_time_minutes=dead_time,
        )

        _LOGGER.info(
            "Calculated anticipation: start at %s (%.1f min) for target %.1f°C at %s (LHS: %.2f°C/h)",
            prediction.anticipated_start_time.isoformat(),
            prediction.estimated_duration_minutes,
            target_temp,
            target_time.isoformat(),
            prediction.learned_heating_slope,
        )

        result = self._create_data_structure(
            anticipated_start_time=prediction.anticipated_start_time,
            next_schedule_time=target_time,
            next_target_temperature=target_temp,
            anticipation_minutes=prediction.estimated_duration_minutes,
            current_temp=current_temp,
            learned_heating_slope=prediction.learned_heating_slope,
            confidence_level=prediction.confidence_level,
            timeslot_id=timeslot_id,
            scheduler_entity=scheduler_entity,
            dead_time=dead_time,
        )

        _LOGGER.debug("Exiting calculate_anticipation_datas() -> %s", "data")
        return result

    def _create_data_structure(
        self,
        anticipated_start_time: datetime | None = None,
        next_schedule_time: datetime | None = None,
        next_target_temperature: float | None = None,
        anticipation_minutes: float | None = None,
        current_temp: float | None = None,
        learned_heating_slope: float | None = None,
        confidence_level: float | None = None,
        timeslot_id: str | None = None,
        scheduler_entity: str | None = None,
        dead_time: float | None = None,
    ) -> dict:
        """Create data structure with provided values or None defaults.

        Returns consistent structure with each field having a value or None.
        """
        return {
            "anticipated_start_time": anticipated_start_time,
            "next_schedule_time": next_schedule_time,
            "next_target_temperature": next_target_temperature,
            "anticipation_minutes": anticipation_minutes,
            "current_temp": current_temp,
            "learned_heating_slope": learned_heating_slope,
            "confidence_level": confidence_level,
            "timeslot_id": timeslot_id,
            "scheduler_entity": scheduler_entity,
            "dead_time": dead_time,
        }

    async def _get_persisted_dead_time_or_default(self) -> float:
        """Return the persisted learned dead time or the configured default.

        When auto_learning is enabled, this method tries to restore the last
        learned dead time from persistent storage. This is the correct fallback
        during startup (before cycle extraction completes) or when cycles do not
        yield a valid dead time.

        Returns:
            Persisted learned dead time if available and positive, otherwise the
            configured default dead time.
        """
        if self._lhs_storage is not None:
            try:
                stored = await self._lhs_storage.get_learned_dead_time()
                if stored is not None and stored > 0:
                    _LOGGER.debug(
                        "Using persisted learned dead_time: %.1f minutes", stored
                    )
                    return stored
                if stored is not None and stored <= 0:
                    _LOGGER.debug(
                        "Ignoring non-positive persisted dead_time %.1f minutes; "
                        "falling back to configured default",
                        stored,
                    )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Failed to read persisted dead time", exc_info=True)

        _LOGGER.debug(
            "No persisted dead_time found, using configured default: %.1f minutes",
            self._default_dead_time_minutes,
        )
        return self._default_dead_time_minutes
