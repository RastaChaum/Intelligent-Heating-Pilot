"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""
from __future__ import annotations

from .climate_commander import HAClimateCommander
from .environment_reader import HAEnvironmentReader
from .model_storage import HAModelStorage
from .scheduler_commander import HASchedulerCommander
from .scheduler_reader import HASchedulerReader
from .cycle_cache import HACycleCache

# Import data adapters with try/except to handle test environments
try:
    from .climate_data_adapter import ClimateDataAdapter
    from .sensor_data_adapter import SensorDataAdapter
    from .weather_data_adapter import WeatherDataAdapter
    _DATA_ADAPTERS_AVAILABLE = True
except ImportError:
    _DATA_ADAPTERS_AVAILABLE = False

# Import data adapters with try/except to handle test environments
try:
    from .climate_data_adapter import ClimateDataAdapter
    from .sensor_data_adapter import SensorDataAdapter
    from .weather_data_adapter import WeatherDataAdapter
    _DATA_ADAPTERS_AVAILABLE = True
except ImportError:
    _DATA_ADAPTERS_AVAILABLE = False

# Import data adapters with try/except to handle test environments
try:
    from .climate_data_adapter import ClimateDataAdapter
    from .sensor_data_adapter import SensorDataAdapter
    from .weather_data_adapter import WeatherDataAdapter
    _DATA_ADAPTERS_AVAILABLE = True
except ImportError:
    _DATA_ADAPTERS_AVAILABLE = False

__all__ = [
    "HAClimateCommander",
    "HAEnvironmentReader",
    "HAModelStorage",
    "HASchedulerCommander",
    "HASchedulerReader",
    "HACycleCache",
]

if _DATA_ADAPTERS_AVAILABLE:
    __all__.extend([
        "ClimateDataAdapter",
        "SensorDataAdapter",
        "WeatherDataAdapter",
    ])
