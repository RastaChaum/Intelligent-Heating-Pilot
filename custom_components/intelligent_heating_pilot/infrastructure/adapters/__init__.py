"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""
from __future__ import annotations

from .climate_commander import HAClimateCommander
from .environment_reader import HAEnvironmentReader
from .historical_data_reader import HAHistoricalDataReader
from .model_storage import HAModelStorage
from .scheduler_commander import HASchedulerCommander
from .scheduler_reader import HASchedulerReader

__all__ = [
    "HAClimateCommander",
    "HAEnvironmentReader",
    "HAHistoricalDataReader",
    "HAModelStorage",
    "HASchedulerCommander",
    "HASchedulerReader",
]
