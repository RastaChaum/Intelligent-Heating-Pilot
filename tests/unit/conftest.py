"""Shared fixtures for all unit tests.

Provides common test infrastructure that should apply across all unit test modules.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def instant_queue_sleep():
    """Bypass long asyncio.sleep calls in RecordingExtractionQueue during tests.

    The queue uses a 10-second inter-task pause (QUEUE_YIELD_SECONDS) to prevent
    recorder saturation in production. In tests this would cause each test that
    calls run_queue() to take 10+ seconds. This fixture replaces asyncio.sleep
    with a version that skips delays >= 1 second while preserving short delays
    used by the test mocks (e.g., 0.01s timing verification sleeps).

    For long delays, we still yield once (asyncio.sleep(0)) so that background
    tasks created with asyncio.create_task() get a chance to run, preserving
    correct event-loop semantics for cancellation tests.
    """
    _original_sleep = asyncio.sleep

    async def _fast_sleep(delay: float, *args, **kwargs) -> None:
        if delay < 1.0:
            await _original_sleep(delay, *args, **kwargs)
        else:
            # Still yield to the event loop so background tasks (e.g. cancel)
            # can execute, but don't wait the full production delay.
            await _original_sleep(0)

    with patch.object(asyncio, "sleep", side_effect=_fast_sleep):
        yield
