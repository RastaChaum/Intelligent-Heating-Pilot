"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""
from __future__ import annotations

from .historical_data_reader import IHistoricalDataReader
from .ml_model_storage import IMLModelStorage
from .model_storage import IModelStorage
from .scheduler_commander import ISchedulerCommander
from .scheduler_reader import ISchedulerReader

__all__ = [
    "IHistoricalDataReader",
    "IMLModelStorage",
    "IModelStorage",
    "ISchedulerCommander",
    "ISchedulerReader",
]
