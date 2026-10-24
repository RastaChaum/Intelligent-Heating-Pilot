"""Root conftest.py to setup Python path for all tests.

This module sets up the Python path to allow imports from the custom component.
All tests must use:
  - from custom_components.intelligent_heating_pilot.domain.value_objects import ...
"""

import asyncio
import sys
from pathlib import Path

# Add repository root to sys.path so that custom_components can be imported
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))


def pytest_runtest_setup(item):
    """Ensure a current event loop exists before each test's fixture setup phase.

    pytest-asyncio (asyncio_mode='auto') sets the loop to None after each async test.
    autouse fixtures from pytest-homeassistant-custom-component (enable_event_loop_debug,
    verify_cleanup) call asyncio.get_event_loop() during their setup phase, which raises
    RuntimeError for sync tests (BDD, domain) that run after async integration tests.

    This hook runs before any fixture, so the loop is ready when those fixtures execute.
    For async tests, pytest-asyncio will replace this loop with its own managed loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
