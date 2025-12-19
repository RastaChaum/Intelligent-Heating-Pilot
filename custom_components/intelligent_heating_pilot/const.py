"""Constants for the Intelligent Heating Pilot integration."""

VERSION = "0.4.0"
DOMAIN = "intelligent_heating_pilot"
# Configuration keys
CONF_NAME = "name"
CONF_VTHERM_ENTITY = "vtherm_entity_id"
CONF_SCHEDULER_ENTITIES = "scheduler_entities"
CONF_HUMIDITY_IN_ENTITY = "humidity_in_entity_id"
CONF_HUMIDITY_OUT_ENTITY = "humidity_out_entity_id"
CONF_CLOUD_COVER_ENTITY = "cloud_cover_entity_id"
CONF_DATA_RETENTION_DAYS = "data_retention_days"  # Retention period for all IHP data (cycles, slopes, etc.)
CONF_LHS_RETENTION_DAYS = "lhs_retention_days"  # Deprecated: Use CONF_DATA_RETENTION_DAYS
CONF_DECISION_MODE = "decision_mode"  # NEW: Choose between 'simple' and 'ml'

# Legacy keys (kept for backward compatibility if needed)
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
DEFAULT_LHS_RETENTION_DAYS = 30  # Deprecated: Use DEFAULT_DATA_RETENTION_DAYS
DEFAULT_DECISION_MODE = DECISION_MODE_SIMPLE  # Simple mode by default

# Service names
SERVICE_CALCULATE_START_TIME = "calculate_start_time"
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
VTHERM_ATTR_SLOPE = "temperature_slope"
VTHERM_ATTR_TEMPERATURE = "temperature"
VTHERM_ATTR_CURRENT_TEMPERATURE = "ema_temp"  # Actual room temperature (exponential moving average)

# Scheduler specific attributes
SCHEDULER_ATTR_NEXT_SCHEDULE = "next_entries"
SCHEDULER_ATTR_NEXT_TIME = "next_time"
SCHEDULER_ATTR_NEXT_ACTION = "next_action"

# Storage
STORAGE_KEY = "intelligent_heating_pilot_storage"
STORAGE_VERSION = 1