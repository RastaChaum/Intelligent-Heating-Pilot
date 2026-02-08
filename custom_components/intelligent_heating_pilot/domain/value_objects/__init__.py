"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""

from __future__ import annotations

from .cycle_cache_data import CycleCacheData
from .environment_state import EnvironmentState
from .heating import HeatingAction, HeatingCycle, HeatingDecision, TariffPeriodDetail
from .historical_data import HistoricalDataKey, HistoricalDataSet, HistoricalMeasurement
from .prediction_result import PredictionResult
from .scheduled_timeslot import ScheduledTimeslot
from .slope_data import SlopeData

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
    "CycleCacheData",
]
