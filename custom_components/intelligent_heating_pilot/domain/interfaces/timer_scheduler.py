"""Timer scheduler interface for anticipation triggering.

This interface abstracts timer scheduling operations, allowing the domain
to schedule anticipation triggers without depending on Home Assistant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Coroutine


class ITimerScheduler(ABC):
    """Interface for scheduling timer-based callbacks.

    This contract allows the application layer to schedule callbacks
    at specific times without coupling to Home Assistant's event loop.
    """

    @abstractmethod
    def schedule_timer(
        self,
        target_time: datetime,
        callback: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Callable[[], None]:
        """Schedule a callback to execute at a specific time.

        Args:
            target_time: When to execute the callback
            callback: Async function to execute at target_time

        Returns:
            Cancel function that can be called to cancel the timer
        """
        pass
