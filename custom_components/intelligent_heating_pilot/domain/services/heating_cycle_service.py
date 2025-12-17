"""Domain service for extracting heating cycles from historical data."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ..interfaces.heating_cycle_service import IHeatingCycleService
from ..value_objects.heating import HeatingCycle, TariffPeriodDetail
from ..value_objects.historical_data import HistoricalDataKey, HistoricalDataSet, HistoricalMeasurement

_LOGGER = logging.getLogger(__name__)


class HeatingCycleService(IHeatingCycleService):
    """Service to detect and extract heating cycles from a raw historical dataset.
    
    This service encapsulates the business logic for defining what constitutes a heating cycle,
    how long cycles should be split, and how relevant metrics are calculated.
    It operates solely on domain value objects and has no direct dependencies on Home Assistant
    or ML frameworks.
    """
    
    def __init__(
        self,
        temp_delta_threshold: float = 0.2,
        cycle_split_duration_minutes: int | None = None,
        min_cycle_duration_minutes: int = 5,
        max_cycle_duration_minutes: int = 300,
    ) -> None:
        """Initialize the HeatingCycleService.

        These parameters are intended to come from the integration configuration (provided
        by the infrastructure layer). Defaults are provided for ease of testing and
        for installs that do not customize the UI options.

        Args:
            temp_delta_threshold: The temperature difference (target - current) in °C
                above which heating is considered active to start a cycle.
            cycle_split_duration_minutes: Optional duration in minutes to split long heating
                cycles into smaller sub-cycles for granular analysis. If None, cycles are not split.
            min_cycle_duration_minutes: Minimum duration for a valid heating cycle.
            max_cycle_duration_minutes: Maximum duration for a single heating cycle (before splitting).
        """
        _LOGGER.info("Entering HeatingCycleService.__init__")
        _LOGGER.debug(
            "Initializing with temp_delta_threshold=%s, cycle_split_duration_minutes=%s, "
            "min_cycle_duration_minutes=%s, max_cycle_duration_minutes=%s",
            temp_delta_threshold,
            cycle_split_duration_minutes,
            min_cycle_duration_minutes,
            max_cycle_duration_minutes,
        )

        self._temp_delta_threshold = temp_delta_threshold
        self._cycle_split_duration_minutes = cycle_split_duration_minutes
        self._min_cycle_duration_minutes = min_cycle_duration_minutes
        self._max_cycle_duration_minutes = max_cycle_duration_minutes

        _LOGGER.info("Exiting HeatingCycleService.__init__")
    
    async def extract_heating_cycles(
        self,
        device_id: str,
        history_data_set: HistoricalDataSet,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract heating cycles from a HistoricalDataSet within a given time range.
        
        This method applies the core business logic to identify and process heating cycles.
        
        Args:
            history_data_set: A HistoricalDataSet containing all necessary raw sensor data.
            start_time: The start of the time range for cycle extraction.
            end_time: The end of the time range for cycle extraction.
            
        Returns:
            A list of HeatingCycle value objects.
            
        Raises:
            ValueError: If critical historical data keys are missing from the dataset.
        """
        _LOGGER.info("Extracting heating cycles from %s to %s", start_time, end_time)
        
        # Validate critical data availability
        self._validate_critical_data(history_data_set)
        
        # Récupérer les données d'historique triées par timestamp
        heating_state_history = sorted(
            history_data_set.data[HistoricalDataKey.HEATING_STATE],
            key=lambda m: m.timestamp,
        )
        
        # Initialiser les variables de suivi de cycle
        heating_start: datetime | None = None
        cycle_start_indoor_temp: float | None = None
        cycle_start_target_temp: float | None = None
        
        cycles: list[HeatingCycle] = []       

        for measurement in heating_state_history:
            timestamp = measurement.timestamp
            # Separate concerns: mode_on (system enabled) vs action_active (actually heating)
            mode_on = self._is_mode_on(measurement)
            action_active = self._is_heating_active(measurement)

            current_indoor_temp, current_target_temp = self._get_temperatures_at(
                history_data_set, timestamp
            )

            if current_indoor_temp is None or current_target_temp is None:
                _LOGGER.debug("Skipping measurement at %s due to missing temp data", timestamp)
                prev_action_active = action_active
                continue

            if heating_start is None:
                # Check for cycle START condition
                if self._should_start_cycle(mode_on, action_active, current_indoor_temp, current_target_temp):
                    heating_start = timestamp
                    cycle_start_indoor_temp = current_indoor_temp
                    cycle_start_target_temp = current_target_temp
                    _LOGGER.debug(
                        "Heating cycle started at %s (Indoor: %.1f, Target: %.1f)",
                        timestamp,
                        current_indoor_temp,
                        current_target_temp,
                    )
            else:
                # Check if cycle should end
                cycle_ended, end_reason = self._should_end_cycle(
                    mode_on, current_indoor_temp, current_target_temp
                )

                if cycle_ended:
                    _LOGGER.debug("Heating cycle ended at %s (Reason: %s)", timestamp, end_reason)
                    created = self._create_cycles(
                        device_id=device_id,
                        start_time=heating_start,
                        end_time=timestamp,
                        start_indoor_temp=cycle_start_indoor_temp if cycle_start_indoor_temp is not None else current_indoor_temp,
                        end_indoor_temp=current_indoor_temp,
                        target_temp=cycle_start_target_temp if cycle_start_target_temp is not None else current_target_temp,
                        history_data_set=history_data_set,
                    )
                    if created:
                        cycles.extend(created)
                    # Reset for next cycle
                    heating_start = None
                    cycle_start_indoor_temp = None
                    cycle_start_target_temp = None
        
        # Gérer un cycle potentiellement non terminé à la fin des données
        if heating_start is not None:
            _LOGGER.debug("Unfinished heating cycle found, ending at data_set end time %s", end_time)
            created = self._create_cycles(
                device_id=device_id,
                start_time=heating_start,
                end_time=end_time,
                start_indoor_temp=cycle_start_indoor_temp or 20.0,
                end_indoor_temp=self._get_value_at_time(history_data_set.data.get(HistoricalDataKey.INDOOR_TEMP, []), end_time, float) or 20.0,
                target_temp=cycle_start_target_temp or 20.0,
                history_data_set=history_data_set,
            )
            if created:
                cycles.extend(created)
            
        _LOGGER.info("Extracted %d heating cycles", len(cycles))
        return cycles
    
    def _is_heating_active(self, measurement: HistoricalMeasurement) -> bool:
        """Determines if the heating system is considered ON from a measurement.
        
        This logic abstracts whether the entity is a climate control, switch, or binary sensor.
        """
        # For action detection, prefer hvac_action attribute when present.
        attrs = measurement.attributes or {}
        hvac_action = attrs.get("hvac_action")

        if hvac_action:
            try:
                if isinstance(hvac_action, str):
                    action = hvac_action.lower()
                else:
                    action = None

                if action in ("heating", "preheating"):
                    return True
            except Exception:
                _LOGGER.debug("Error evaluating hvac_action: %s", attrs, exc_info=True)

        # Fallback: non-climate entities (binary sensor, switch) or missing attrs
        if isinstance(measurement.value, str):
            state = measurement.value.lower()
            return state in ("on", "heat", "heating", "true", "1")
        return bool(measurement.value)

    def _is_mode_on(self, measurement: HistoricalMeasurement) -> bool:
        """Determines if the heating system is enabled (mode indicates heating allowed).

        This checks `hvac_mode` against Home Assistant's heating-related modes.
        Falls back to truthiness of the measurement value when attributes are missing.
        """
        attrs = measurement.attributes or {}
        hvac_mode = attrs.get("hvac_mode")

        if hvac_mode:
            try:
                if isinstance(hvac_mode, str):
                    mode = hvac_mode.lower()
                else:
                    mode = None
                return mode in ("heat", "heat_cool", "auto")
            except Exception:
                _LOGGER.debug("Error evaluating hvac_mode: %s", attrs, exc_info=True)

        # Fallback for non-climate entities
        if isinstance(measurement.value, str):
            state = measurement.value.lower()
            return state in ("on", "true", "1")
        return bool(measurement.value)

    def _get_value_at_time(
        self,
        history: list[HistoricalMeasurement],
        target_time: datetime,
        value_type: type,
        attribute_name: str | None = None,
    ) -> Any | None:
        """Get the sensor value at or before a specific time from a list of HistoricalMeasurement.
        
        Args:
            history: List of HistoricalMeasurement records for the entity.
            target_time: Time to find the value for.
            value_type: The expected type of the value (e.g., float, str).
            attribute_name: If provided, extract value from attributes (e.g., 'current_temperature').
            
        Returns:
            The sensor value cast to value_type, or None if not found/invalid.
        """
        closest_measurement: HistoricalMeasurement | None = None
        
        # Find the closest measurement at or before target_time
        for measurement in history:
            if measurement.timestamp <= target_time:
                if closest_measurement is None or measurement.timestamp > closest_measurement.timestamp:
                    closest_measurement = measurement
        
        if closest_measurement:
            try:
                value_raw: Any = None
                if attribute_name:
                    value_raw = closest_measurement.attributes.get(attribute_name)
                else:
                    value_raw = closest_measurement.value
                
                if value_raw is not None:
                    return value_type(value_raw)
            except (ValueError, TypeError):
                _LOGGER.debug("Could not cast value %s to %s for timestamp %s",
                              value_raw, value_type.__name__, closest_measurement.timestamp)
        return None

    def _create_cycles(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        start_indoor_temp: float,
        end_indoor_temp: float,
        target_temp: float,
        history_data_set: HistoricalDataSet,
    ) -> list[HeatingCycle]:
        """Build and return one or more HeatingCycle objects for the provided time range.

        This function no longer mutates an external list; it returns the created cycle(s)
        so the caller can decide what to do with them (append, persist, filter...).
        """
        duration_minutes = (end_time - start_time).total_seconds() / 60.0

        if not (
            duration_minutes >= self._min_cycle_duration_minutes
            and duration_minutes <= self._max_cycle_duration_minutes
            and start_indoor_temp is not None
            and end_indoor_temp is not None
            and target_temp is not None
        ):
            _LOGGER.debug("Skipping invalid cycle due to duration or missing temp data.")
            return []

        # Compute energy, runtime and tariff breakdown using helper methods
        data = history_data_set.data
        
        total_energy_kwh = self._compute_energy_kwh(data, start_time, end_time)
        heating_duration_minutes = self._compute_runtime_minutes(
            data, start_time, end_time, duration_minutes
        )
        
        tariff_history = data.get(HistoricalDataKey.TARIFF_PRICE_EUR_PER_KWH, [])
        energy_history = data.get(HistoricalDataKey.HEATING_ENERGY_KWH, [])
        runtime_history = data.get(HistoricalDataKey.HEATING_RUNTIME_SECONDS, [])

        total_cost_euro, tariff_details = self._compute_tariff_breakdown(
            tariff_history, energy_history, runtime_history,
            start_time, end_time, total_energy_kwh
        )

        # Build HeatingCycle with computed tariff details (may be empty)
        cycle = HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_indoor_temp,
            start_temp=start_indoor_temp,
            tariff_details=tariff_details,
        )
        _LOGGER.debug(
            "Created single heating cycle: %s (energy=%.3fkWh duration=%.1fmin cost=%.3f€)",
            cycle,
            total_energy_kwh,
            heating_duration_minutes,
            total_cost_euro,
        )

        # If splitting is enabled, return sub-cycles (used for ML augmentation).
        if self._cycle_split_duration_minutes is not None and duration_minutes > self._cycle_split_duration_minutes:
            return self._split_into_cycles(device_id, start_time, end_time, start_indoor_temp, end_indoor_temp, target_temp, history_data_set)

        return [cycle]

    def _split_into_cycles(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        start_indoor_temp: float,
        end_indoor_temp: float,
        target_temp: float,
        history_data_set: HistoricalDataSet,
    ) -> list[HeatingCycle]:
        """Splits a long heating cycle into smaller sub-cycles and returns them."""
        if self._cycle_split_duration_minutes is None:  # Should not happen if called correctly
            return []

        # Ensure temperatures are available before attempting numeric operations
        if start_indoor_temp is None or end_indoor_temp is None:
            _LOGGER.debug("Missing start or end indoor temp for splitting; skipping split")
            return []

        duration_minutes = (end_time - start_time).total_seconds() / 60.0
        num_sub_cycles = int(duration_minutes / self._cycle_split_duration_minutes)
        remaining_minutes = duration_minutes - (num_sub_cycles * self._cycle_split_duration_minutes)

        if duration_minutes == 0:
            return []

        temp_per_minute = (end_indoor_temp - start_indoor_temp) / duration_minutes

        current_sub_cycle_start_time = start_time
        current_sub_cycle_start_temp = start_indoor_temp

        created: list[HeatingCycle] = []

        _LOGGER.debug(
            "Splitting cycle from %s to %s (%.1f min) into %d sub-cycles",
            start_time,
            end_time,
            duration_minutes,
            num_sub_cycles + (1 if remaining_minutes > 0 else 0),
        )

        for i in range(num_sub_cycles):
            sub_cycle_end_time = current_sub_cycle_start_time + timedelta(minutes=self._cycle_split_duration_minutes)
            sub_cycle_end_temp = current_sub_cycle_start_temp + (temp_per_minute * self._cycle_split_duration_minutes)

            sub_cycle = HeatingCycle(
                device_id=device_id,
                start_time=current_sub_cycle_start_time,
                end_time=sub_cycle_end_time,
                target_temp=target_temp,  # Target remains constant for sub-cycles
                end_temp=sub_cycle_end_temp,
                start_temp=current_sub_cycle_start_temp,
                tariff_details=[],  # TODO: calculate for sub-cycle
            )
            created.append(sub_cycle)
            _LOGGER.debug("  Created sub-cycle %d: %s", i + 1, sub_cycle)

            current_sub_cycle_start_time = sub_cycle_end_time
            current_sub_cycle_start_temp = sub_cycle_end_temp

        # Record remaining part if significant
        if remaining_minutes > 0:
            remaining_end_time = current_sub_cycle_start_time + timedelta(minutes=remaining_minutes)
            remaining_cycle = HeatingCycle(
                device_id=device_id,
                start_time=current_sub_cycle_start_time,
                end_time=remaining_end_time,
                target_temp=target_temp,
                end_temp=end_indoor_temp,
                start_temp=current_sub_cycle_start_temp,
                tariff_details=[],  # TODO: calculate for remaining sub-cycle
            )
            created.append(remaining_cycle)
            _LOGGER.debug("  Created remaining sub-cycle: %s", remaining_cycle)

        return created
    
    def _compute_energy_kwh(
        self,
        data: dict[HistoricalDataKey, list[HistoricalMeasurement]],
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """Compute energy consumed during cycle using cumulative meter (preferred) or fallback to 0.0.
        
        Args:
            data: Historical data dictionary
            start_time: Cycle start time
            end_time: Cycle end time
            
        Returns:
            Energy consumed in kWh (≥0.0)
        """
        energy_history = data.get(HistoricalDataKey.HEATING_ENERGY_KWH, [])
        if energy_history:
            start_energy = self._get_value_at_time(energy_history, start_time, float)
            end_energy = self._get_value_at_time(energy_history, end_time, float)
            if start_energy is not None and end_energy is not None:
                return max(0.0, end_energy - start_energy)
        return 0.0

    def _compute_runtime_minutes(
        self,
        data: dict[HistoricalDataKey, list[HistoricalMeasurement]],
        start_time: datetime,
        end_time: datetime,
        fallback_duration_minutes: float,
    ) -> float:
        """Compute actual heating runtime by summing on_time_sec snapshots.
        
        HEATING_RUNTIME_SECONDS is NOT cumulative; it's the instantaneous "On" duration
        at each snapshot (reset after each cycle). Sum all values in the time range to get
        the total runtime across all sub-cycles within [start_time, end_time].
        
        Args:
            data: Historical data dictionary
            start_time: Cycle start time
            end_time: Cycle end time
            fallback_duration_minutes: Temporal duration to use if no runtime sensor
            
        Returns:
            Heating runtime in minutes (≥0.0)
        """
        runtime_history = data.get(HistoricalDataKey.HEATING_RUNTIME_SECONDS, [])
        if runtime_history:
            total_runtime_seconds = 0.0
            for measurement in runtime_history:
                if start_time <= measurement.timestamp <= end_time:
                    try:
                        value = float(measurement.value)
                        total_runtime_seconds += value
                    except (TypeError, ValueError):
                        continue
            if total_runtime_seconds > 0.0:
                return total_runtime_seconds / 60.0
        return fallback_duration_minutes

    def _compute_tariff_breakdown(
        self,
        tariff_history: list[HistoricalMeasurement],
        energy_history: list[HistoricalMeasurement],
        runtime_history: list[HistoricalMeasurement],
        start_time: datetime,
        end_time: datetime,
        fallback_energy_kwh: float,
    ) -> tuple[float, list[TariffPeriodDetail]]:
        """Compute cost and tariff period details by segmenting cycle at tariff price changes.
        
        For each segment between consecutive tariff price changes:
        - Energy: difference in cumulative meter (HEATING_ENERGY_KWH)
        - Runtime: sum of on_time_sec values (HEATING_RUNTIME_SECONDS, non-cumulative) in segment
        - Cost: energy_kwh × price
        
        Args:
            tariff_history: Tariff price measurements (EUR/kWh)
            energy_history: Cumulative energy measurements (kWh)
            runtime_history: Non-cumulative on_time_sec measurements (seconds)
            start_time: Cycle start time
            end_time: Cycle end time
            fallback_energy_kwh: Energy to use if no cumulative meter
            
        Returns:
            Tuple of (total_cost_euro, tariff_details_list)
        """
        if not tariff_history or not energy_history:
            return 0.0, []

        t_samples = sorted(tariff_history, key=lambda m: m.timestamp)
        start_price = self._get_value_at_time(t_samples, start_time, float) or 0.0
        
        # Build segment boundaries at tariff price changes
        boundaries: list[datetime] = [start_time]
        prev_price = start_price
        for m in t_samples:
            if m.timestamp <= start_time:
                continue
            if m.timestamp > end_time:
                break
            try:
                p = float(m.value)
            except (TypeError, ValueError):
                continue
            if p != prev_price:
                boundaries.append(m.timestamp)
                prev_price = p
        boundaries.append(end_time)

        total_cost_euro = 0.0
        total_segment_energy = 0.0
        tariff_details: list[TariffPeriodDetail] = []

        for a, b in zip(boundaries[:-1], boundaries[1:]):
            # Energy consumed in segment (from cumulative meter)
            start_energy = self._get_value_at_time(energy_history, a, float) or 0.0
            end_energy = self._get_value_at_time(energy_history, b, float) or 0.0
            energy_segment = max(0.0, end_energy - start_energy)

            # Price applicable at segment start
            price = self._get_value_at_time(t_samples, a, float) or 0.0
            cost_segment = energy_segment * price

            # Runtime in segment: sum on_time_sec values within [a, b] or use temporal duration
            if runtime_history:
                segment_runtime_seconds = 0.0
                for measurement in runtime_history:
                    if a <= measurement.timestamp < b:
                        try:
                            segment_runtime_seconds += float(measurement.value)
                        except (TypeError, ValueError):
                            continue
                segment_runtime_minutes = segment_runtime_seconds / 60.0 if segment_runtime_seconds > 0.0 else (b - a).total_seconds() / 60.0
            else:
                segment_runtime_minutes = (b - a).total_seconds() / 60.0

            tariff_details.append(
                TariffPeriodDetail(
                    tariff_price_eur_per_kwh=price,
                    energy_kwh=energy_segment,
                    heating_duration_minutes=segment_runtime_minutes,
                    cost_euro=cost_segment,
                )
            )

            total_segment_energy += energy_segment
            total_cost_euro += cost_segment

        return total_cost_euro, tariff_details

    def _validate_critical_data(self, history_data_set: HistoricalDataSet) -> None:
        """Validate that critical historical data keys are present in the dataset.
        
        Args:
            history_data_set: Dataset to validate
            
        Raises:
            ValueError: If any critical key is missing
        """
        required_keys = [
            HistoricalDataKey.INDOOR_TEMP,
            HistoricalDataKey.TARGET_TEMP,
            HistoricalDataKey.HEATING_STATE,
        ]
        for key in required_keys:
            if not history_data_set.data.get(key):
                raise ValueError(f"Missing critical historical data for key: {key.value}")

    def _get_temperatures_at(
        self,
        history_data_set: HistoricalDataSet,
        timestamp: datetime,
    ) -> tuple[float | None, float | None]:
        """Get indoor and target temperatures at a given timestamp.
        
        Args:
            history_data_set: Dataset containing temperature histories
            timestamp: Time to query
            
        Returns:
            Tuple of (indoor_temp, target_temp), either may be None if unavailable
        """
        indoor_temp = self._get_value_at_time(
            history_data_set.data.get(HistoricalDataKey.INDOOR_TEMP, []),
            timestamp,
            float,
        )
        target_temp = self._get_value_at_time(
            history_data_set.data.get(HistoricalDataKey.TARGET_TEMP, []),
            timestamp,
            float,
        )
        return indoor_temp, target_temp

    def _should_start_cycle(
        self,
        mode_on: bool,
        action_active: bool,
        indoor_temp: float | None,
        target_temp: float | None,
    ) -> bool:
        """Check if heating cycle should start based on system state and temperatures.
        
        Cycle starts when ALL conditions are met:
        - System enabled (mode_on)
        - Heating action active
        - Temperature below target minus threshold
        
        Args:
            mode_on: Whether climate system is enabled
            action_active: Whether heating action is currently active
            indoor_temp: Current indoor temperature (may be None)
            target_temp: Current target temperature (may be None)
            
        Returns:
            True if cycle should start
        """
        if not mode_on or not action_active:
            return False
        if indoor_temp is None or target_temp is None:
            return False
        temp_delta = target_temp - indoor_temp
        return temp_delta > self._temp_delta_threshold

    def _should_end_cycle(
        self,
        mode_on: bool,
        indoor_temp: float | None,
        target_temp: float | None,
    ) -> tuple[bool, str]:
        """Check if heating cycle should end and return reason if so.
        
        Cycle ends when ANY condition is met:
        - Indoor temperature reaches target (within threshold)
        - System disabled (mode_on=False)
        
        Args:
            mode_on: Whether climate system is enabled
            indoor_temp: Current indoor temperature (may be None)
            target_temp: Current target temperature (may be None)
            
        Returns:
            Tuple of (should_end, reason_string)
        """
        if not mode_on:
            return True, "mode_disabled"
        if indoor_temp is not None and target_temp is not None:
            if indoor_temp >= (target_temp - self._temp_delta_threshold):
                return True, "target_reached_or_within_threshold"
        return False, ""
