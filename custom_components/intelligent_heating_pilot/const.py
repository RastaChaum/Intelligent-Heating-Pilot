"""Constants for the Intelligent Heating Pilot integration."""

from .domain.constants import (  # noqa: F401  re-exported for the Home Assistant layers
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_CLIMATE_ENTITY,
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_MAX_CYCLE_DURATION_MINUTES,
    CONF_MIN_CYCLE_DURATION_MINUTES,
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
    CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    CONF_PRESET_TEMPERATURES,
    CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
    CONF_SCHEDULER_ENTITIES,
    CONF_TASK_RANGE_DAYS,
    CONF_TEMP_DELTA_THRESHOLD,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_WAKE_UP_SOURCES,
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NATIVE_SCHEDULE_DRIVE,
    DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
    DEFAULT_NATIVE_SCHEDULE_PRESET_KEY,
    DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
    DEFAULT_TASK_RANGE_DAYS,
    DEFAULT_TEMP_DELTA_THRESHOLD,
)

VERSION = "0.7.1"
DOMAIN = "intelligent_heating_pilot"
# The central configuration is a config entry of this domain holding the values devices inherit.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_CENTRAL = "central"
CENTRAL_UNIQUE_ID = "central_configuration"
CENTRAL_ENTRY_TITLE = "Central configuration"
# The title is stored with the entry, so it cannot be a translation key: it follows the language
# Home Assistant runs in when the entry is created.
CENTRAL_ENTRY_TITLES = {"fr": "Configuration centrale"}
# hass.data[DOMAIN] key of the central values the devices were last reloaded with.
CENTRAL_APPLIED_KEY = "central_applied_values"
EVENT_DEAD_TIME_UPDATED = f"{DOMAIN}_dead_time_updated"
# Configuration keys
CONF_NAME = "name"
CONF_DATA_RETENTION_DAYS = (
    "data_retention_days"  # Retention period for all IHP data (cycles, slopes, etc.)
)
CONF_DECISION_MODE = "decision_mode"  # NEW: Choose between 'simple' and 'ml'

# Heating Cycle Detection Parameters
CONF_IHP_ENABLED = "ihp_enabled"  # Enable/disable IHP preheating
CONF_THERMAL_SLOPE_ENTITY = "thermal_slope_entity"
CONF_CURRENT_TEMP_ENTITY = "current_temp_entity"
CONF_CURRENT_HUMIDITY_ENTITY = "current_humidity_entity"
CONF_TARGET_TEMP_ENTITY = "target_temp_entity"
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"
CONF_OUTDOOR_HUMIDITY_ENTITY = "outdoor_humidity_entity"
CONF_CLOUD_COVERAGE_ENTITY = "cloud_coverage_entity"
CONF_SCHEDULER_ENTITY = "scheduler_entity"

# Decision modes
DECISION_MODE_SIMPLE = "simple"  # Rule-based decisions (no ML)
DECISION_MODE_ML = "ml"  # AI-powered decisions (requires IHP-ML-Models)

# Default values
DEFAULT_NAME = "Intelligent Heating Pilot"
DEFAULT_DATA_RETENTION_DAYS = 30  # Keep IHP data (cycles, slopes, etc.) for 30 days
DEFAULT_DECISION_MODE = DECISION_MODE_SIMPLE  # Simple mode by default

# Default values for Heating Cycle Detection

# Safety shutoff grace period: brief interruptions shorter than this threshold (e.g. frost/safety mode)
# will NOT terminate an in-progress heating cycle, preventing bogus slope values.
# Note: 10 minutes is the recommended production default (enabled for all new/upgraded devices).
# HeatingCycleService.__init__ defaults to 0 for test-isolation purposes; production always reads
# this value from HA config (or falls back to DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES).

# Native schedule (schedule.*) options. A native schedule's blocks carry free "data" with no
# convention on the keys, so the user says which keys hold a preset or a temperature, and
# whether IHP may apply the next block itself. Off by default: native schedules stay
# compute-only unless the user opts in.
SERVICE_CALCULATE_ANTICIPATED_START_TIME = "calculate_anticipated_start_time"
SERVICE_SCHEDULER_RUN_ACTION = "run_action"

# Attributes
ATTR_START_TIME = "start_time"
ATTR_ANTICIPATED_START_TIME = "anticipated_start_time"
ATTR_NEXT_SCHEDULE_TIME = "next_schedule_time"
ATTR_NEXT_TARGET_TEMP = "next_target_temperature"
ATTR_PREHEAT_DURATION = "preheat_duration_minutes"
ATTR_CURRENT_TEMP = "current_temperature"
ATTR_CURRENT_HUMIDITY = "current_humidity"
ATTR_TARGET_TEMP = "target_temperature"
ATTR_OUTDOOR_TEMP = "outdoor_temperature"
ATTR_OUTDOOR_HUMIDITY = "outdoor_humidity"
ATTR_CLOUD_COVERAGE = "cloud_coverage"
ATTR_TARGET_TIME = "target_time"
ATTR_THERMAL_SLOPE = "thermal_slope"
ATTR_LEARNED_HEATING_SLOPE = "learned_heating_slope"
ATTR_MAX_HEATING_SLOPE = "max_heating_slope"

# VTherm specific attributes
VTHERM_ATTR_TEMPERATURE = "temperature"
VTHERM_ATTR_CURRENT_TEMPERATURE = "ema_temp"  # Actual room temperature (exponential moving average)

# Scheduler specific attributes
SCHEDULER_ATTR_NEXT_SCHEDULE = "next_entries"
SCHEDULER_ATTR_NEXT_TIME = "next_time"
SCHEDULER_ATTR_NEXT_ACTION = "next_action"

# Storage
STORAGE_KEY = "intelligent_heating_pilot_storage"
STORAGE_VERSION = 1

# Wake-up sources (#66): entities holding a point in time that IHP anticipates like a slot.
# Stored as a list of objects in the entry options, per IHP; absent means none.
CONF_WAKE_UP_ENTITY = "entity_id"
CONF_WAKE_UP_FROM_SCHEDULE = "target_from_schedule"
CONF_WAKE_UP_PRESET = "target_preset"
CONF_WAKE_UP_TEMPERATURE = "target_temperature"
CONF_WAKE_UP_HORIZON_HOURS = "horizon_hours"
CONF_WAKE_UP_HOLD_MINUTES = "hold_minutes"
DEFAULT_WAKE_UP_HORIZON_HOURS = 24
MIN_WAKE_UP_HORIZON_HOURS = 1
MAX_WAKE_UP_HORIZON_HOURS = 72
MAX_WAKE_UP_HOLD_MINUTES = 720
