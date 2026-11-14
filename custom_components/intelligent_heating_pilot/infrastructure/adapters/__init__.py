"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""

from __future__ import annotations

from .climate_commander import HAClimateCommander
from .climate_data_reader import HAClimateDataReader
from .context_reader import HAContextReader
from .environment_reader import HAEnvironmentReader
from .hacs_run_action_actuator import HacsRunActionActuator
from .heating_cycle_storage import HAHeatingCycleStorage
from .lhs_storage import HALhsStorage
from .preheat_record_storage import HAPreheatRecordStorage
from .scheduler_ownership_resolver import HASchedulerOwnershipResolver
from .scheduler_reader import HASchedulerReader
from .sensor_data_reader import HASensorDataReader
from .sun_reader import HASunReader
from .timer_scheduler import HATimerScheduler
from .weather_data_reader import HAWeatherDataReader

__all__ = [
    "HAClimateCommander",
    "HAClimateDataReader",
    "HAEnvironmentReader",
    "HAContextReader",
    "HALhsStorage",
    "HAPreheatRecordStorage",
    "HASchedulerOwnershipResolver",
    "HacsRunActionActuator",
    "HASchedulerReader",
    "HAHeatingCycleStorage",
    "HATimerScheduler",
    "HASensorDataReader",
    "HASunReader",
    "HAWeatherDataReader",
]
