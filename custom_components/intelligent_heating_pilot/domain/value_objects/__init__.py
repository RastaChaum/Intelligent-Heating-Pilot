"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""
from __future__ import annotations

from .cycle_features import CycleFeatures
from .environment_state import EnvironmentState
from .heating_cycle import HeatingCycle
from .heating_decision import HeatingAction, HeatingDecision
from .prediction_result import PredictionResult
from .room_features import RoomFeatures
from .schedule_timeslot import ScheduleTimeslot
from .slope_data import SlopeData
from .training_data import TrainingDataset, TrainingExample

__all__ = [
    "CycleFeatures",
    "EnvironmentState",
    "HeatingAction",
    "HeatingCycle",
    "HeatingDecision",
    "PredictionResult",
    "RoomFeatures",
    "ScheduleTimeslot",
    "SlopeData",
    "TrainingDataset",
    "TrainingExample",
]
