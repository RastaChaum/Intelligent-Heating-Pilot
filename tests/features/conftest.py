"""pytest-bdd configuration and shared fixtures for BDD tests.

This file provides shared fixtures and configuration for all BDD feature tests.

## pytest-bdd and pytest-homeassistant-custom-component Integration (WORKAROUND)

PROBLEM: pytest-homeassistant-custom-component's enable_event_loop_debug fixture
invokes asyncio.get_event_loop() without protecting against RuntimeError.
For BDD tests (sync), no event loop is created by pytest-asyncio.

SOLUTION:
1. Create session-scope event loop in pytest_configure
2. Monkeypatch asyncio.get_event_loop to never raise RuntimeError
3. Use auto-use fixture to ensure loop exists at test time
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle

# Store reference to main event loop
_MAIN_EVENT_LOOP = None


def pytest_configure(config):
    """Create event loop that persists for entire session."""
    global _MAIN_EVENT_LOOP

    # Create a new event loop for this thread
    try:
        _MAIN_EVENT_LOOP = asyncio.get_event_loop()
        if _MAIN_EVENT_LOOP.is_closed():
            raise RuntimeError("Loop is closed")
    except RuntimeError:
        _MAIN_EVENT_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_MAIN_EVENT_LOOP)


def pytest_sessionstart(session):
    """Monkeypatch asyncio.get_event_loop to never fail for BDD tests.

    This prevents pytest-homeassistant-custom-component's enable_event_loop_debug
    fixture from raising RuntimeError when there's no event loop.
    """
    global _MAIN_EVENT_LOOP

    original_get_event_loop = asyncio.get_event_loop

    def patched_get_event_loop():
        """Return main loop or create new one - never raise RuntimeError."""
        if _MAIN_EVENT_LOOP and not _MAIN_EVENT_LOOP.is_closed():
            return _MAIN_EVENT_LOOP

        try:
            loop = original_get_event_loop()
            if not loop.is_closed():
                return loop
        except RuntimeError:
            pass

        # Fallback: create new loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    # Monkeypatch the global asyncio function
    asyncio.get_event_loop = patched_get_event_loop


@pytest.fixture(scope="function", autouse=True)
def _bdd_event_loop_restore():
    """Restore event loop for each test (in case it got cleared)."""
    global _MAIN_EVENT_LOOP

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
    except RuntimeError:
        if _MAIN_EVENT_LOOP and not _MAIN_EVENT_LOOP.is_closed():
            asyncio.set_event_loop(_MAIN_EVENT_LOOP)
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    yield


@pytest.fixture
def base_datetime() -> datetime:
    """Base datetime for BDD scenarios."""
    return datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def device_id() -> str:
    """Device ID for BDD scenarios."""
    return "climate.test_vtherm"


def create_test_heating_cycle(
    device_id: str,
    start_time: datetime,
    duration_hours: float = 1.0,
    target_temp: float = 20.5,
    end_temp: float = 20.0,
    start_temp: float = 18.0,
) -> HeatingCycle:
    """Helper to create a test heating cycle for BDD scenarios.

    Args:
        device_id: The device identifier
        start_time: When the heating cycle started
        duration_hours: Duration of the cycle in hours
        target_temp: Target temperature
        end_temp: Temperature at end of cycle
        start_temp: Temperature at start of cycle

    Returns:
        A HeatingCycle instance for testing
    """
    end_time = start_time + timedelta(hours=duration_hours)
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=target_temp,
        end_temp=end_temp,
        start_temp=start_temp,
        tariff_details=None,
    )
