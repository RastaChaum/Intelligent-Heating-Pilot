"""Recorder access queue for serializing Home Assistant recorder queries.

Provides a FIFO queue (asyncio.Lock) shared across all IHP device instances
to prevent parallel recorder access that can overwhelm Home Assistant,
especially at startup or during cache refresh with multiple IHP devices.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

RECORDER_QUEUE_KEY = "recorder_queue"


class RecorderAccessQueue:
    """FIFO queue for serializing recorder access across all IHP instances.

    Uses an asyncio.Lock to ensure that only one IHP device queries the
    recorder at a time. asyncio.Lock is FIFO: waiters are served in the
    order they requested the lock.

    This prevents performance issues when multiple IHP devices simultaneously
    query the recorder (e.g., at HA startup or during periodic cache refresh).
    """

    def __init__(self) -> None:
        """Initialize the recorder access queue."""
        self._lock = asyncio.Lock()
        _LOGGER.debug("RecorderAccessQueue initialized")

    @property
    def lock(self) -> asyncio.Lock:
        """Return the asyncio.Lock for use as an async context manager.

        Usage:
            async with recorder_queue.lock:
                # Perform recorder query
        """
        return self._lock


def get_recorder_queue(hass: HomeAssistant) -> RecorderAccessQueue:
    """Get or create the shared RecorderAccessQueue for this HA instance.

    The queue is stored in hass.data[DOMAIN][RECORDER_QUEUE_KEY] and shared
    across all IHP device entries to serialize recorder access.

    Args:
        hass: Home Assistant instance

    Returns:
        The shared RecorderAccessQueue instance
    """
    domain_data = hass.data.setdefault(DOMAIN, {})

    if RECORDER_QUEUE_KEY not in domain_data:
        domain_data[RECORDER_QUEUE_KEY] = RecorderAccessQueue()
        _LOGGER.debug("Created shared RecorderAccessQueue in hass.data[%s]", DOMAIN)

    # Type cast for mypy since domain_data is typed as dict[str, Any]
    return domain_data[RECORDER_QUEUE_KEY]  # type: ignore[no-any-return]
