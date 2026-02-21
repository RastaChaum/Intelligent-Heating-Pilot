"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""

from __future__ import annotations

from .climate_commander import HAClimateCommander
from .climate_data_adapter import ClimateDataAdapter
from .climate_data_reader import HAClimateDataReader
from .context_reader import HAContextReader
from .environment_reader import HAEnvironmentReader
from .heating_cycle_storage import HAHeatingCycleStorage
from .lhs_storage import HALhsStorage
from .scheduler_commander import HASchedulerCommander
from .scheduler_reader import HASchedulerReader
from .sensor_data_adapter import SensorDataAdapter
from .timer_scheduler import HATimerScheduler
from .weather_data_adapter import WeatherDataAdapter

__all__ = [
    "HAClimateCommander",
    "HAClimateDataReader",
    "HAEnvironmentReader",
    "HAContextReader",
    "HALhsStorage",
    "HASchedulerCommander",
    "HASchedulerReader",
    "HAHeatingCycleStorage",
    "HATimerScheduler",
    "ClimateDataAdapter",
    "SensorDataAdapter",
    "WeatherDataAdapter",
]
