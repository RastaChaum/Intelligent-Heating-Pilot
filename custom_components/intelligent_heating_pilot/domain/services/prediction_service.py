"""Prediction service for calculating heating times."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from ..constants import (
    BASE_HIGH_CONFIDENCE,
    BASE_LOW_CONFIDENCE,
    BASE_MEDIUM_CONFIDENCE,
    CLOUD_COVERAGE_FACTOR,
    CONFIDENCE_BOOST_PER_SENSOR,
    DEFAULT_ANTICIPATION_BUFFER,
    HIGH_CONFIDENCE_SLOPE,
    HUMIDITY_FACTOR,
    HUMIDITY_REFERENCE,
    MAX_ANTICIPATION_TIME,
    MEDIUM_CONFIDENCE_SLOPE,
    MIN_ANTICIPATION_TIME,
)
from ..value_objects import DaylightPeriod, PredictionResult

_LOGGER = logging.getLogger(__name__)


class PredictionService:
    """Service for predicting heating start times.

    This service contains the core prediction algorithm that determines
    when heating should start to reach target temperature at a scheduled time.

    The calculation considers:
    1. Learned dead time: the emitter's delay before the room responds
    2. Temperature difference to heat and learned heating slope (LHS)
    3. Humidity effects on heating efficiency
    4. Solar gain from cloud coverage, while the sun is up

    The environmental correction applies to the heating phase (ΔT / LHS) only.
    The dead time belongs to the emitter: sun or humidity does not make it
    respond faster (#257).
    """

    def predict_heating_time(
        self,
        current_temp: float | None,
        target_temp: float,
        learned_slope: float,
        target_time: datetime,
        humidity: float | None = None,
        cloud_coverage: float | None = None,
        dead_time_minutes: float = 0.0,
        daylight_periods: Sequence[DaylightPeriod] = (),
    ) -> PredictionResult:
        """Calculate when heating should start.

        Args:
            current_temp: Current room temperature in Celsius (None = cannot calculate)
            target_temp: Target temperature in Celsius
            learned_slope: Learned heating slope in °C/hour
            target_time: When target should be reached (mandatory)
            humidity: Indoor humidity percentage (0-100) (optional)
            cloud_coverage: Cloud coverage percentage (0-100, 0=clear sky) (optional)
            dead_time_minutes: Dead time in minutes (initial period with minimal heating effect)
            daylight_periods: Periods between sunrise and sunset around the heating phase.
                None known means no solar gain: a preheat planned a little early beats
                a late one.

        Returns:
            Prediction result with start time and confidence
        """
        # Handle missing current temperature
        if current_temp is None:
            _LOGGER.warning("Cannot calculate prediction: current_temp is None")
            return PredictionResult(
                anticipated_start_time=target_time,
                estimated_duration_minutes=0.0,
                confidence_level=0.0,
                learned_heating_slope=learned_slope,
            )

        # Calculate temperature difference
        temp_delta = target_temp - current_temp

        if temp_delta <= 0:
            # Already at target, anticipated start time = target time
            _LOGGER.debug(
                "Already at target temperature (%.1f°C >= %.1f°C), no heating needed",
                current_temp,
                target_temp,
            )
            return PredictionResult(
                anticipated_start_time=target_time,
                estimated_duration_minutes=0.0,
                confidence_level=1.0,
                learned_heating_slope=learned_slope,
            )

        # Protection against invalid slope (should not happen with proper validation)
        if learned_slope is None or learned_slope <= 0:
            _LOGGER.error(
                "CRITICAL: Invalid learned heating slope (%.4f°C/h <= 0) reached prediction_service. "
                "This indicates missing validation in calling code. Cannot calculate prediction.",
                learned_slope or 0,
            )
            return PredictionResult(
                anticipated_start_time=target_time,
                estimated_duration_minutes=0.0,
                confidence_level=0.0,
                learned_heating_slope=learned_slope or 0,
            )

        # anticipation = dead_time + heating × correction: the dead time is never corrected
        heating_minutes = (temp_delta / learned_slope) * 60.0
        daylight_fraction = self._daylight_fraction(
            target_time - timedelta(minutes=heating_minutes), target_time, daylight_periods
        )
        correction_factor = self._calculate_environmental_correction(
            humidity, cloud_coverage, daylight_fraction
        )
        anticipation_minutes = dead_time_minutes + heating_minutes * correction_factor

        # Apply buffer and limits
        anticipation_minutes += DEFAULT_ANTICIPATION_BUFFER
        anticipation_minutes = max(
            MIN_ANTICIPATION_TIME, min(MAX_ANTICIPATION_TIME, anticipation_minutes)
        )

        # Calculate anticipated start time
        anticipated_start = target_time - timedelta(minutes=anticipation_minutes)

        # Calculate confidence level based on slope and available environmental data
        confidence = self._calculate_confidence(learned_slope, humidity)

        _LOGGER.debug(
            "Prediction: ΔT=%.1f°C, slope=%.2f°C/h, dead_time=%.1f min, correction=%.2f, "
            "duration=%.1f min, confidence=%.2f",
            temp_delta,
            learned_slope,
            dead_time_minutes,
            correction_factor,
            anticipation_minutes,
            confidence,
        )

        return PredictionResult(
            anticipated_start_time=anticipated_start,
            estimated_duration_minutes=anticipation_minutes,
            confidence_level=confidence,
            learned_heating_slope=learned_slope,
        )

    @staticmethod
    def _daylight_fraction(
        heating_start: datetime,
        heating_end: datetime,
        daylight_periods: Sequence[DaylightPeriod],
    ) -> float:
        """Return the share of the heating phase spent between sunrise and sunset.

        The window uses the uncorrected heating duration: the correction stays
        within ±20 %, so the window barely moves, and this avoids solving for a
        window that depends on its own correction.

        Args:
            heating_start: Start of the heating phase (after the dead time)
            heating_end: When the target must be reached
            daylight_periods: Daylight periods around the heating phase

        Returns:
            Fraction between 0.0 (all in the dark) and 1.0 (all in daylight)
        """
        heating_minutes = (heating_end - heating_start).total_seconds() / 60.0
        if heating_minutes <= 0:
            return 0.0
        daylight_minutes = sum(
            period.overlap_minutes(heating_start, heating_end) for period in daylight_periods
        )
        return min(1.0, daylight_minutes / heating_minutes)

    def _calculate_environmental_correction(
        self,
        humidity: float | None,
        cloud_coverage: float | None,
        daylight_fraction: float = 0.0,
    ) -> float:
        """Calculate the correction factor of the heating phase.

        This method combines multiple environmental factors that affect
        heating efficiency:
        - Indoor humidity (thermal mass effect)
        - Cloud coverage (solar gain), scaled by the share of the heating
          phase spent in daylight: a clear sky does not warm a room at night

        Outdoor temperature is deliberately absent. The learned slope comes from
        recent cycles and already reflects recent weather, so a correction anchored
        on a fixed reference temperature counted the cold twice. A correction relative
        to the weather of the learning cycles needs their outdoor temperature, which
        cycles now record (``HeatingCycle.avg_outdoor_temp``).

        Args:
            humidity: Indoor humidity percentage (0-100)
            cloud_coverage: Cloud coverage percentage (0-100)
            daylight_fraction: Share of the heating phase between sunrise and sunset

        Returns:
            Combined correction factor (>1 means slower heating)
        """
        correction_factor = 1.0

        # Humidity factor: higher humidity makes heating feel slower
        # Formula: humidity_factor = 1 + (humidity - HUMIDITY_REFERENCE) * HUMIDITY_FACTOR
        # At 50% humidity: factor = 1.0 (neutral)
        # At 80% humidity: factor = 1.06 (6% slower)
        # At 20% humidity: factor = 0.94 (6% faster)
        if humidity is not None:
            humidity_factor = 1.0 + (humidity - HUMIDITY_REFERENCE) * HUMIDITY_FACTOR
            humidity_factor = max(0.8, min(1.2, humidity_factor))
            correction_factor *= humidity_factor
            _LOGGER.debug("Humidity %.1f%% -> factor %.2f", humidity, humidity_factor)

        # Solar gain factor: less cloud coverage means more solar heat gain
        # Formula: solar_factor = 1 - (100 - cloud_coverage) * CLOUD_COVERAGE_FACTOR
        # At 100% cloud: factor = 1.0 (no solar gain)
        # At 0% cloud (clear sky): factor = 0.9 (10% faster due to sun)
        # At 50% cloud: factor = 0.95 (5% faster)
        # Only the daylight share of the heating phase gets the solar shortening.
        if cloud_coverage is not None:
            solar_factor = 1.0 - (100.0 - cloud_coverage) * CLOUD_COVERAGE_FACTOR
            solar_factor = max(0.8, min(1.0, solar_factor))
            solar_factor = 1.0 - (1.0 - solar_factor) * daylight_fraction
            correction_factor *= solar_factor
            _LOGGER.debug(
                "Cloud coverage %.1f%%, %.0f%% of heating in daylight -> factor %.2f",
                cloud_coverage,
                daylight_fraction * 100.0,
                solar_factor,
            )

        return correction_factor

    def _calculate_confidence(
        self,
        learned_slope: float,
        humidity: float | None,
    ) -> float:
        """Calculate confidence level in the prediction.

        Confidence is based on:
        - Slope validity (higher slope = better learning)
        - Available environmental data used by the prediction

        Args:
            learned_slope: Learned heating slope in °C/hour
            humidity: Indoor humidity (if available)

        Returns:
            Confidence level between 0.0 and 1.0
        """
        # Base confidence from slope validity
        if learned_slope > HIGH_CONFIDENCE_SLOPE:
            confidence = BASE_HIGH_CONFIDENCE
        elif learned_slope > MEDIUM_CONFIDENCE_SLOPE:
            confidence = BASE_MEDIUM_CONFIDENCE
        else:
            confidence = BASE_LOW_CONFIDENCE

        # Adjust confidence based on available environmental data
        data_availability = 0
        if humidity is not None:
            data_availability += 1

        # Increase confidence slightly with more environmental data
        confidence += data_availability * CONFIDENCE_BOOST_PER_SENSOR

        # Cap at 1.0
        return min(1.0, confidence)
