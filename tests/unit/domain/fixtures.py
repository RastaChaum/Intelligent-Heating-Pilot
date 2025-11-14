"""Centralized test fixtures for domain layer tests (DRY principle)."""
from datetime import datetime, timedelta


def get_test_datetime() -> datetime:
    """Get a fixed datetime for testing.
    
    Returns:
        A datetime object representing 2024-01-15 12:00:00
    """
    return datetime(2024, 1, 15, 12, 0, 0)


def get_future_datetime(hours: int = 2) -> datetime:
    """Get a future datetime for testing.
    
    Args:
        hours: Number of hours in the future
        
    Returns:
        A datetime object in the future
    """
    return get_test_datetime() + timedelta(hours=hours)


# Standard test values
TEST_CURRENT_TEMP = 18.0
TEST_TARGET_TEMP = 21.0
TEST_OUTDOOR_TEMP = 10.0
TEST_HUMIDITY = 50.0
TEST_LEARNED_SLOPE = 2.0
TEST_CLOUD_COVERAGE = 50.0

# Test timeslot ID
TEST_TIMESLOT_ID = "test_timeslot_1"
