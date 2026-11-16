"""Fixtures of the end-to-end tests: opt-in, and a Home Assistant container for the module.

They need Docker and about ten minutes, so they only run when ``IHP_E2E=1`` is set: the default
``pytest tests/`` skips them, and the release-candidate workflow turns them on.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.integration.real_components.fetch import ComponentFetchError, fetch_components

E2E_FLAG = "IHP_E2E"
IMAGE_VARIABLE = "IHP_E2E_HA_IMAGE"
LOG_DIR_VARIABLE = "IHP_E2E_LOG_DIR"
REPOSITORY_ROOT = Path(__file__).parents[2]

_COMPONENTS_ROOT: str | None
try:
    _COMPONENTS_ROOT = str(fetch_components().parent)
except ComponentFetchError:
    _COMPONENTS_ROOT = None
if _COMPONENTS_ROOT is not None and _COMPONENTS_ROOT not in sys.path:
    # The thermostat's constants are imported to build its configuration entry
    sys.path.append(_COMPONENTS_ROOT)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the end-to-end tests unless they are asked for and Docker is there."""
    reason = None
    if not os.environ.get(E2E_FLAG):
        reason = f"set {E2E_FLAG}=1 to run the end-to-end tests"
    elif shutil.which("docker") is None:
        reason = "Docker is not available"
    elif _COMPONENTS_ROOT is None:
        reason = "the third-party components could not be downloaded"
    for item in items:
        if "tests/e2e" not in str(item.fspath):
            continue
        # The Home Assistant test plugin blocks sockets; these tests talk to a container
        item.add_marker(pytest.mark.enable_socket)
        if reason is not None:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("ihp-e2e")


@pytest.fixture(scope="module")
def components_root() -> Path:
    assert _COMPONENTS_ROOT is not None
    return Path(_COMPONENTS_ROOT) / "custom_components"


@pytest.fixture(scope="module")
def ha_image() -> str:
    from tests.e2e.stack import DEFAULT_IMAGE

    return os.environ.get(IMAGE_VARIABLE, DEFAULT_IMAGE)


@pytest.fixture(scope="module")
def container_logs(workdir: Path) -> Iterator[Path]:
    """Where the container log is saved, so a failed run leaves something to read."""
    directory = Path(os.environ.get(LOG_DIR_VARIABLE) or workdir)
    directory.mkdir(parents=True, exist_ok=True)
    yield directory / "home-assistant.log"
