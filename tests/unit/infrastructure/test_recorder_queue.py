"""Unit tests for RecorderAccessQueue (FIFO recorder serialization)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RECORDER_QUEUE_KEY,
    RecorderAccessQueue,
    get_recorder_queue,
)


class TestRecorderAccessQueue:
    """Tests for RecorderAccessQueue."""

    def test_lock_is_asyncio_lock(self):
        """Verify the queue exposes an asyncio.Lock."""
        queue = RecorderAccessQueue()
        assert isinstance(queue.lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_lock_serializes_access(self):
        """Verify concurrent tasks are serialized through the lock (FIFO)."""
        queue = RecorderAccessQueue()
        execution_order: list[int] = []

        async def task(task_id: int, delay: float) -> None:
            async with queue.lock:
                execution_order.append(task_id)
                await asyncio.sleep(delay)

        # Start 3 tasks; task 1 holds the lock longest, so 2 and 3 queue behind it
        t1 = asyncio.create_task(task(1, 0.05))
        await asyncio.sleep(0.01)  # Give task 1 time to acquire lock
        t2 = asyncio.create_task(task(2, 0.01))
        t3 = asyncio.create_task(task(3, 0.01))

        await asyncio.gather(t1, t2, t3)

        # Tasks should execute in FIFO order: 1, 2, 3
        assert execution_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_lock_prevents_parallel_execution(self):
        """Verify that only one task runs inside the lock at a time."""
        queue = RecorderAccessQueue()
        concurrent_count = 0
        max_concurrent = 0

        async def task() -> None:
            nonlocal concurrent_count, max_concurrent
            async with queue.lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.01)
                concurrent_count -= 1

        tasks = [asyncio.create_task(task()) for _ in range(5)]
        await asyncio.gather(*tasks)

        assert max_concurrent == 1


class TestGetRecorderQueue:
    """Tests for get_recorder_queue helper."""

    def test_creates_queue_on_first_call(self):
        """First call creates and stores RecorderAccessQueue in hass.data."""
        hass = MagicMock()
        hass.data = {}

        queue = get_recorder_queue(hass)

        assert isinstance(queue, RecorderAccessQueue)
        assert RECORDER_QUEUE_KEY in hass.data["intelligent_heating_pilot"]

    def test_returns_same_instance_on_subsequent_calls(self):
        """Subsequent calls return the same RecorderAccessQueue instance."""
        hass = MagicMock()
        hass.data = {}

        queue1 = get_recorder_queue(hass)
        queue2 = get_recorder_queue(hass)

        assert queue1 is queue2

    def test_works_with_existing_domain_data(self):
        """Queue creation works when DOMAIN key already exists in hass.data."""
        hass = MagicMock()
        hass.data = {"intelligent_heating_pilot": {"some_entry": "value"}}

        queue = get_recorder_queue(hass)

        assert isinstance(queue, RecorderAccessQueue)
        # Original data should be preserved
        assert hass.data["intelligent_heating_pilot"]["some_entry"] == "value"
