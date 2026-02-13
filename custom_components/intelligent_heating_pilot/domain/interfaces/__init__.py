"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""

from __future__ import annotations

from .decision_strategy_interface import IDecisionStrategy
from .device_config_reader_interface import IDeviceConfigReader
from .heating_cycle_service_interface import IHeatingCycleService
from .heating_cycle_storage_interface import IHeatingCycleStorage
from .historical_data_adapter_interface import IHistoricalDataAdapter
from .lhs_storage_interface import ILhsStorage
from .scheduler_commander_interface import ISchedulerCommander
from .scheduler_reader_interface import ISchedulerReader
from .sensor_data_adapter_interface import ISensorDataAdapter
from .timer_scheduler import ITimerScheduler
from .weather_data_adapter_interface import IWeatherDataAdapter

__all__ = [
    "ISchedulerReader",
    "ILhsStorage",
    "ISchedulerCommander",
    "IDecisionStrategy",
    "IHeatingCycleService",
    "IHeatingCycleStorage",
    "IDeviceConfigReader",
    "IHistoricalDataAdapter",
    "ISensorDataAdapter",
    "IWeatherDataAdapter",
    "ITimerScheduler",
]
