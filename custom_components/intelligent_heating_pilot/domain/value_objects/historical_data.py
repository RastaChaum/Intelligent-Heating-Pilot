"""Value objects for historical data within the heating domain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class HistoricalDataKey(Enum):
    """Keys to identify different types of historical data within a dataset."""
    
    INDOOR_TEMP = "indoor_temp"
    OUTDOOR_TEMP = "outdoor_temp"
    TARGET_TEMP = "target_temp"
    HEATING_STATE = "heating_state"
    HUMIDITY = "humidity"
    # Optional instrumentation for energy & tariff calculations
    HEATING_ENERGY_KWH = "heating_energy_kwh"  # Cumulative energy meter in kWh
    HEATING_RUNTIME_SECONDS = "heating_runtime_seconds"  # Cumulative runtime in seconds
    TARIFF_PRICE_EUR_PER_KWH = "tariff_price_eur_per_kwh"  # Tariff price time series
    # Ajoutez d'autres clés au besoin


@dataclass(frozen=True)
class HistoricalMeasurement:
    """Represents a single historical measurement for an entity at a specific timestamp.
    
    Attributes:
        timestamp: The datetime when the measurement was recorded.
        value: The main state value of the entity (e.g., temperature, 'on'/'off').
        attributes: A dictionary of additional attributes (e.g., for climate entities like 'hvac_action').
    """
    
    timestamp: datetime
    value: float | str | bool
    attributes: dict[str, Any]


@dataclass(frozen=True)
class HistoricalDataSet:
    """A collection of historical measurements, categorized by a HistoricalDataKey.
    
    This serves as a domain-agnostic representation of raw historical sensor data
    before it's processed into domain-specific concepts like heating cycles.
    
    Attributes:
        data: A dictionary where keys are HistoricalDataKey and values are lists of HistoricalMeasurement.
    """
    
    data: dict[HistoricalDataKey, list[HistoricalMeasurement]]
