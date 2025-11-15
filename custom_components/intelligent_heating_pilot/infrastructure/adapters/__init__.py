"""Adapters implementing domain interfaces using Home Assistant APIs.

This module contains thin adapter classes that translate between Home Assistant
entities/services and domain value objects. Adapters contain NO business logic.
"""
from __future__ import annotations

from .scheduler_reader import HASchedulerReader
from .model_storage import HAModelStorage
from .scheduler_commander import HASchedulerCommander

__all__ = [
    "HASchedulerReader",
    "HAModelStorage",
    "HASchedulerCommander",
]
