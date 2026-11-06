"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""

from __future__ import annotations

from .contextual_lhs_by_hour import ContextualLHSByHour
from .daylight_period import DaylightPeriod
from .environment_state import EnvironmentState
from .heating import HeatingAction, HeatingCycle, HeatingDecision, TariffPeriodDetail
from .heating_cycle_cache_data import HeatingCycleCacheData
from .historical_data import HistoricalDataKey, HistoricalDataSet, HistoricalMeasurement
from .prediction_result import PredictionResult
from .recording_extraction_task import ExtractionTaskState, RecordingExtractionTask
from .scheduled_timeslot import ScheduledTimeslot
from .slope_data import SlopeData

__all__ = [
    "ContextualLHSByHour",
    "DaylightPeriod",
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
    "HeatingCycleCacheData",
    "RecordingExtractionTask",
    "ExtractionTaskState",
]
