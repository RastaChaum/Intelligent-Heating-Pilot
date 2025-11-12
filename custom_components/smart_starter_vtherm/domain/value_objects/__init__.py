"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""
from __future__ import annotations

from .environment_state import EnvironmentState
from .schedule_event import ScheduleEvent
from .prediction_result import PredictionResult
from .heating_decision import HeatingDecision, HeatingAction

__all__ = [
    "EnvironmentState",
    "ScheduleEvent",
    "PredictionResult",
    "HeatingDecision",
    "HeatingAction",
]
