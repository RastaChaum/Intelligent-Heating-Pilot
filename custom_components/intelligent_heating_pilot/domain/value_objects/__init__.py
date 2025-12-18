"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""
from __future__ import annotations

from .environment_state import EnvironmentState
from .scheduled_timeslot import ScheduledTimeslot
from .prediction_result import PredictionResult
from .heating import HeatingDecision, HeatingAction, HeatingCycle, TariffPeriodDetail
from .slope_data import SlopeData
from .historical_data import HistoricalDataKey, HistoricalDataSet, HistoricalMeasurement
from .lhs_cache_entry import LHSCacheEntry

__all__ = [
    "EnvironmentState",
    "ScheduledTimeslot",
    "PredictionResult",
    "HeatingDecision",
    "HeatingAction",
    "HeatingCycle",
    "TariffPeriodDetail",
    "SlopeData",
    "HistoricalDataKey",
    "HistoricalDataSet",
    "HistoricalMeasurement",
    "LHSCacheEntry",
]
