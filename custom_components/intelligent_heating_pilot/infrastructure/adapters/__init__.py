"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""

from __future__ import annotations

from .climate_commander import HAClimateCommander
from .climate_data_adapter import ClimateDataAdapter
from .cycle_cache import HACycleCache
from .environment_reader import HAEnvironmentReader
from .model_storage import HAModelStorage
from .scheduler_commander import HASchedulerCommander
from .scheduler_reader import HASchedulerReader
from .cycle_cache import HACycleCache
from .timer_scheduler import HATimerScheduler
from .climate_data_adapter import ClimateDataAdapter
from .sensor_data_adapter import SensorDataAdapter
from .weather_data_adapter import WeatherDataAdapter

__all__ = [
    "HAClimateCommander",
    "HAEnvironmentReader",
    "HAModelStorage",
    "HASchedulerCommander",
    "HASchedulerReader",
    "HACycleCache",
    "HATimerScheduler",
    "ClimateDataAdapter",
    "SensorDataAdapter",
    "WeatherDataAdapter",
]
