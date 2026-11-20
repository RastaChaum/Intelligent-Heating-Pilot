"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""

from __future__ import annotations

from .central_config_reader_interface import ICentralConfigReader
from .climate_commander_interface import IClimateCommander
from .climate_data_reader_interface import IClimateDataReader
from .context_reader_interface import IContextReader
from .decision_strategy_interface import IDecisionStrategy
from .device_config_reader_interface import IDeviceConfigReader
from .environment_reader_interface import IEnvironmentReader
from .heating_cycle_service_interface import IHeatingCycleService
from .heating_cycle_storage_interface import IHeatingCycleStorage
from .historical_data_adapter_interface import IHistoricalDataAdapter
from .lhs_storage_interface import ILhsStorage
from .preheat_actuator_interface import IPreheatActuator
from .preheat_record_store_interface import IPreheatRecordStore
from .preset_temperature_resolver_interface import IPresetTemperatureResolver
from .schedule_slot_lookup_interface import IScheduleSlotLookup
from .scheduler_ownership_resolver_interface import ISchedulerOwnershipResolver
from .scheduler_reader_interface import ISchedulerReader
from .sun_reader_interface import ISunReader
from .timer_scheduler import ITimerScheduler
from .wake_up_source_reader_interface import IWakeUpSourceReader

__all__ = [
    "ICentralConfigReader",
    "IClimateCommander",
    "IClimateDataReader",
    "IPreheatActuator",
    "IPresetTemperatureResolver",
    "IWakeUpSourceReader",
    "IPreheatRecordStore",
    "IScheduleSlotLookup",
    "ISchedulerOwnershipResolver",
    "ISchedulerReader",
    "IEnvironmentReader",
    "IContextReader",
    "ILhsStorage",
    "IDecisionStrategy",
    "IHeatingCycleService",
    "IHeatingCycleStorage",
    "IDeviceConfigReader",
    "IHistoricalDataAdapter",
    "ITimerScheduler",
    "ISunReader",
]
