"""Domain constants for heating prediction business logic.

These constants define the business rules for heating anticipation calculations.
They are part of the domain layer and independent of infrastructure concerns.
"""

# Anticipation time constraints (in minutes)
MIN_ANTICIPATION_TIME = 10  # Minimum anticipation before heating starts
MAX_ANTICIPATION_TIME = 360  # Maximum anticipation (6 hours)
DEFAULT_ANTICIPATION_BUFFER = 5  # Safety buffer to ensure target is reached on time

# Heating slope thresholds (in °C/hour)
MIN_VALID_SLOPE = 0.1  # Minimum valid heating slope (technical threshold)
# Former speed floor of the learning rule. A cycle is now excluded for an explicit
# disturbance signal, not for its speed (#255). Cycles cached before their disturbance
# was recorded keep this floor: some of them are safety-mode cycles (#223).
LEGACY_MINIMUM_REALISTIC_LHS = 0.2
DEFAULT_LEARNED_SLOPE = 2.0  # Default slope when no learning data exists

# Presets VTherm applies by itself when it cannot heat normally: "power" while shedding
# load (overpowering), "safety" when its temperature sensors stop reporting. They are
# the only disturbance signals the Recorder keeps: VTherm does not record its safety,
# power and window manager states. A cycle during which one is recorded is not learned,
# except for a load shedding shorter than the grace period: it is bridged within the
# cycle, like a brief window opening (#260).
LOAD_SHEDDING_PRESET = "power"
SAFETY_PRESET = "safety"
DISTURBANCE_PRESETS = frozenset({LOAD_SHEDDING_PRESET, SAFETY_PRESET})

# Dead time (in minutes)
DEFAULT_DEAD_TIME_MINUTES = 0.0  # Default dead time when no learning data exists
# Indoor temperature rise (°C) that ends a cycle's dead time: above typical sensor noise,
# yet sensitive enough to catch early heat propagation.
DEAD_TIME_TEMP_RISE_C = 0.2
# A cycle's heating phase ends at its first plateau: a reading after which the room gains
# less than PLATEAU_RISE_TOLERANCE_C (one sensor step) for at least
# PLATEAU_MIN_DURATION_MINUTES. A TPI thermostat often settles a few tenths below its
# target; counting that plateau as heating time lowered the learned slope at every
# preheat (#267). A room still warming faster than 0.1 °C/h is never on a plateau.
PLATEAU_RISE_TOLERANCE_C = 0.1
PLATEAU_MIN_DURATION_MINUTES = 60
# Absorbs floating-point error when comparing a temperature difference with a threshold
# (18.2 - 18.0 is 0.19999999999999929); far below any sensor resolution.
TEMP_FLOAT_TOLERANCE_C = 1e-6

# Environmental correction factors
HUMIDITY_REFERENCE = 50.0  # Reference humidity percentage
HUMIDITY_FACTOR = 0.002  # Impact factor per humidity percentage point
CLOUD_COVERAGE_FACTOR = 0.001  # Solar gain factor per cloud coverage percentage

# Confidence thresholds
HIGH_CONFIDENCE_SLOPE = 1.5  # Slope threshold for high confidence (°C/h)
MEDIUM_CONFIDENCE_SLOPE = 0.5  # Slope threshold for medium confidence (°C/h)
BASE_HIGH_CONFIDENCE = 0.9  # Base confidence with good slope
BASE_MEDIUM_CONFIDENCE = 0.75  # Base confidence with medium slope
BASE_LOW_CONFIDENCE = 0.6  # Base confidence with low slope
CONFIDENCE_BOOST_PER_SENSOR = 0.05  # Confidence increase per environmental sensor

# Scheduler action verification
# Absorbs floating-point representation noise only (VTherm's own step is 0.1-0.5°C);
# not a user-facing tuning knob.
TARGET_TEMP_MATCH_TOLERANCE_C = 0.05
# Longest wait for the VTherm to apply a triggered scheduler action. scheduler-component
# returns from run_action before the climate entity has changed (8 ms later in the #256
# logs); past this delay with no matching target, the scheduler is reported blocked.
ACTION_EFFECT_TIMEOUT_SECONDS = 10.0
# HACS Scheduler's run_action looks for the timeslot at the given time on the day it is
# called. A preheat starting the day before its slot therefore does nothing on a schedule
# that does not run today (#250): the same scheduler is retried this long after the
# slot's local midnight, so that the scheduler's "today" is the slot's day.
SLOT_DAY_RETRY_DELAY_SECONDS = 60
# Within this delay of a slot, cancelling a preheat is a completion, not a cancellation: the
# scheduler is about to apply the very same action, so restoring the earlier state would undo it
# for a moment, or for good when the scheduler skips an action that already has its effect.
PREHEAT_RESTORE_GUARD_MINUTES = 5

# Temperature that feeds the anticipation when a slot only names a preset and the thermostat
# does not publish that preset's temperature (the same stand-in native schedules use).
DEFAULT_PRESET_TEMPERATURE_C = 20.0

# A wake-up source does not necessarily change at its deadline: the recalculation that completes
# the preheat and starts its hold is requested this long after it, once the deadline has passed.
DEADLINE_RECALC_DELAY_SECONDS = 1

# Setting keys and built-in defaults of the configurable settings. They are declared here, in the
# domain, so that the settings catalog depends only on domain code; `const.py` re-exports them.
CONF_CLIMATE_ENTITY = "vtherm_entity_id"
CONF_SCHEDULER_ENTITIES = "scheduler_entities"
CONF_HUMIDITY_IN_ENTITY = "humidity_in_entity_id"
CONF_HUMIDITY_OUT_ENTITY = "humidity_out_entity_id"
CONF_TEMPERATURE_OUT_ENTITY = "temperature_out_entity_id"
CONF_CLOUD_COVER_ENTITY = "cloud_cover_entity_id"
CONF_LHS_RETENTION_DAYS = "lhs_retention_days"
CONF_DEAD_TIME_MINUTES = "dead_time_minutes"
CONF_AUTO_LEARNING = "auto_learning"
CONF_TEMP_DELTA_THRESHOLD = "temp_delta_threshold"
CONF_CYCLE_SPLIT_DURATION_MINUTES = "cycle_split_duration_minutes"
CONF_MIN_CYCLE_DURATION_MINUTES = "min_cycle_duration_minutes"
CONF_MAX_CYCLE_DURATION_MINUTES = "max_cycle_duration_minutes"
CONF_TASK_RANGE_DAYS = "task_range_days"
CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES = "anticipation_recalc_tolerance_minutes"
CONF_SAFETY_SHUTOFF_GRACE_MINUTES = "safety_shutoff_grace_minutes"
CONF_NATIVE_SCHEDULE_DRIVE = "native_schedule_drive"
CONF_NATIVE_SCHEDULE_PRESET_KEY = "native_schedule_preset_key"
CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY = "native_schedule_temperature_key"
CONF_NATIVE_SCHEDULE_FALLBACK_PRESET = "native_schedule_fallback_preset"
CONF_WAKE_UP_SOURCES = "wake_up_sources"
DEFAULT_LHS_RETENTION_DAYS = 30
DEFAULT_AUTO_LEARNING = True
DEFAULT_TASK_RANGE_DAYS = 7
DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES = 15
DEFAULT_TEMP_DELTA_THRESHOLD = 0.2
DEFAULT_CYCLE_SPLIT_DURATION_MINUTES = 0
DEFAULT_MIN_CYCLE_DURATION_MINUTES = 5
DEFAULT_MAX_CYCLE_DURATION_MINUTES = 300
DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES = 10
DEFAULT_NATIVE_SCHEDULE_DRIVE = False
DEFAULT_NATIVE_SCHEDULE_PRESET_KEY = "preset"
DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY = "temperature"
DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET = "comfort"
# Temperature the user maps to each preset of a climate that does not publish it (#252),
# stored as {preset name: temperature}
CONF_PRESET_TEMPERATURES = "preset_temperatures"
