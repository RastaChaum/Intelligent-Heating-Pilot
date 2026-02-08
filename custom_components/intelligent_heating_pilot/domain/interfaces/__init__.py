"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""

from __future__ import annotations

from .cycle_cache_interface import ICycleCache
from .decision_strategy_interface import IDecisionStrategy
from .device_config_reader_interface import IDeviceConfigReader
from .heating_cycle_service_interface import IHeatingCycleService
from .historical_data_adapter_interface import IHistoricalDataAdapter
from .model_storage_interface import IModelStorage
from .scheduler_commander_interface import ISchedulerCommander
from .scheduler_reader_interface import ISchedulerReader
from .sensor_data_adapter_interface import ISensorDataAdapter
from .timer_scheduler import ITimerScheduler
from .weather_data_adapter_interface import IWeatherDataAdapter

__all__ = [
    "ISchedulerReader",
    "IModelStorage",
    "ISchedulerCommander",
    "IDecisionStrategy",
    "IHeatingCycleService",
    "ICycleCache",
    "IDeviceConfigReader",
    "IHistoricalDataAdapter",
    "ISensorDataAdapter",
    "IWeatherDataAdapter",
    "ITimerScheduler",
]
