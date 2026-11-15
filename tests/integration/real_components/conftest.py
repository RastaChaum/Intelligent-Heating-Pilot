"""Fixtures that load the real scheduler and thermostat integrations next to IHP."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder

from tests.integration.real_components.fetch import ComponentFetchError, fetch_components


def _fetch_at_collection() -> tuple[str | None, str]:
    """Download the pinned components while collecting, since tests run with DNS disabled."""
    try:
        return str(fetch_components().parent), ""
    except ComponentFetchError as err:
        return None, str(err)


_COMPONENTS_PATH, _FETCH_ERROR = _fetch_at_collection()
if _COMPONENTS_PATH is not None and _COMPONENTS_PATH not in sys.path:
    # ``custom_components`` is a namespace package: any ``sys.path`` entry holding a
    # ``custom_components`` directory contributes to it. Done at import so test modules can
    # import the components' constants while collecting.
    sys.path.append(_COMPONENTS_PATH)


@pytest.fixture(scope="session")
def real_components_path() -> str:
    """Root holding the fetched ``custom_components`` directory; skip the test when they could not be fetched."""
    if _COMPONENTS_PATH is None:
        pytest.skip(f"Real components unavailable: {_FETCH_ERROR}")
    return _COMPONENTS_PATH


@pytest.fixture
def real_components(
    recorder_mock: Recorder, real_components_path: str, enable_custom_integrations: None
) -> None:
    """Let the Home Assistant loader find the fetched components beside IHP.

    ``recorder_mock`` is listed first: it must be set up before ``hass``, which the loader
    fixture depends on.
    """
    assert real_components_path in sys.path


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    """A controllable wall clock that leaves the event loop's own timing alone.

    The usual ``freezer`` also freezes ``time.monotonic``, so any wait with a timeout inside
    Home Assistant or a component never expires and the test hangs. Here only wall-clock time
    is frozen, which is what schedules and timers fired by ``async_fire_time_changed`` read.
    """
    with freeze_time(real_asyncio=True) as frozen:
        yield frozen
