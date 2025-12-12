"""Domain interfaces - contracts for external interactions.

These abstract base classes define how the domain interacts with
the outside world without coupling to specific implementations.
"""
from __future__ import annotations

from .scheduler_reader import ISchedulerReader
from .model_storage import IModelStorage
from .scheduler_commander import ISchedulerCommander
from .decision_strategy import IDecisionStrategy

__all__ = [
    "ISchedulerReader",
    "IModelStorage",
    "ISchedulerCommander",
    "IDecisionStrategy",
]
