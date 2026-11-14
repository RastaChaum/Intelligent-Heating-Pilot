"""Value objects for the domain layer.

Value objects are immutable data carriers that represent concepts in the domain.
"""

from __future__ import annotations

from .actuation_result import ActuationResult
from .cancel_reason import CancelReason
from .climate_snapshot import ClimateSnapshot
from .contextual_lhs_by_hour import ContextualLHSByHour
from .daylight_period import DaylightPeriod
from .environment_state import EnvironmentState
from .heating import HeatingAction, HeatingCycle, HeatingDecision, TariffPeriodDetail
from .heating_cycle_cache_data import HeatingCycleCacheData
from .historical_data import HistoricalDataKey, HistoricalDataSet, HistoricalMeasurement
from .prediction_result import PredictionResult
from .preheat_record import PreheatRecord
from .preheat_recovery import PreheatRecovery, RecoveryOutcome
from .recording_extraction_task import ExtractionTaskState, RecordingExtractionTask
from .restore_decision import RestoreDecision
from .restore_fields import RestoreFields
from .scheduled_timeslot import ScheduledTimeslot
from .scheduler_kind import SchedulerKind
from .slope_data import SlopeData
from .slot_action import SlotAction, SlotActionKind

__all__ = [
    "ContextualLHSByHour",
    "DaylightPeriod",
    "EnvironmentState",
    "ScheduledTimeslot",
    "ActuationResult",
    "CancelReason",
    "ClimateSnapshot",
    "PreheatRecord",
    "PreheatRecovery",
    "RecoveryOutcome",
    "RestoreDecision",
    "RestoreFields",
    "SchedulerKind",
    "SlotAction",
    "SlotActionKind",
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
