"""Constants for the Smart Starter VTherm integration."""

DOMAIN = "smart_starter_vtherm"

# Configuration keys
CONF_NAME = "name"
CONF_CURRENT_TEMP_ENTITY = "current_temp_entity"
CONF_TARGET_TEMP_ENTITY = "target_temp_entity"
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"
CONF_THERMAL_SLOPE = "thermal_slope"
CONF_SCHEDULER_ENTITY = "scheduler_entity"

# Default values
DEFAULT_NAME = "Smart Starter VTherm"
DEFAULT_THERMAL_SLOPE = 2.0  # degrees Celsius per hour

# Service names
SERVICE_CALCULATE_START_TIME = "calculate_start_time"

# Attributes
ATTR_START_TIME = "start_time"
ATTR_PREHEAT_DURATION = "preheat_duration_minutes"
ATTR_CURRENT_TEMP = "current_temperature"
ATTR_TARGET_TEMP = "target_temperature"
ATTR_OUTDOOR_TEMP = "outdoor_temperature"
ATTR_TARGET_TIME = "target_time"
