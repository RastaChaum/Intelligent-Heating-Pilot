"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""

from __future__ import annotations

from .climate_data_reader_interface import IClimateDataReader
from .context_reader_interface import IContextReader
from .decision_strategy_interface import IDecisionStrategy
from .device_config_reader_interface import IDeviceConfigReader
from .environment_reader_interface import IEnvironmentReader
from .heating_cycle_service_interface import IHeatingCycleService
from .heating_cycle_storage_interface import IHeatingCycleStorage
from .historical_data_adapter_interface import IHistoricalDataAdapter
from .lhs_storage_interface import ILhsStorage
from .scheduler_commander_interface import ISchedulerCommander
from .scheduler_reader_interface import ISchedulerReader
from .timer_scheduler import ITimerScheduler

__all__ = [
    "IClimateDataReader",
    "ISchedulerReader",
    "IEnvironmentReader",
    "IContextReader",
    "ILhsStorage",
    "ISchedulerCommander",
    "IDecisionStrategy",
    "IHeatingCycleService",
    "IHeatingCycleStorage",
    "IDeviceConfigReader",
    "IHistoricalDataAdapter",
    "ITimerScheduler",
]
