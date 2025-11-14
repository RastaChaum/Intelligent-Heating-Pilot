"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""
from __future__ import annotations

from .environment_state import EnvironmentState
from .schedule_timeslot import ScheduleTimeslot
from .prediction_result import PredictionResult
from .heating_decision import HeatingDecision, HeatingAction

__all__ = [
    "EnvironmentState",
    "ScheduleTimeslot",
    "PredictionResult",
    "HeatingDecision",
    "HeatingAction",
]
