"""A disposable Home Assistant, started from the official image with IHP and its companions.

Why: the in-process tests run IHP inside the test harness. A release candidate also has to load,
configure and survive a restart in the real Home Assistant, with the real integrations next to it.
The stack builds a configuration directory, starts a container, creates a user through the
onboarding API and exposes the REST and WebSocket APIs. Time is the real one: scenarios schedule
their slots a few minutes ahead.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

DEFAULT_IMAGE = "ghcr.io/home-assistant/home-assistant:2026.10.4"
CONTAINER_PORT = 8123
TIMEZONE = "Europe/Paris"
READY_TIMEOUT_SECONDS = 300
POLL_SECONDS = 3
HTTP_TIMEOUT_SECONDS = 30
CLIENT_ID = "http://ihp-e2e.local/"
USER = {"name": "e2e", "username": "e2e", "password": "e2e-pass-123", "language": "en"}
REPO_COMPONENT = Path(__file__).parents[2] / "custom_components" / "intelligent_heating_pilot"
IGNORED_COPY = shutil.ignore_patterns("__pycache__", "*.pyc")


class StackError(RuntimeError):
    """The Home Assistant container did not behave as the scenario needs."""


@dataclass(frozen=True)
class Room:
    """One heated room: a thermostat over a switch, with a sensor to read and a heater to drive."""

    key: str

    @property
    def name(self) -> str:
        return f"{self.key.title()} Room"

    @property
    def thermostat(self) -> str:
        return f"climate.{self.key}_room"

    @property
    def sensor(self) -> str:
        return f"input_number.{self.key}_temperature"

    @property
    def heater(self) -> str:
        return f"input_boolean.{self.key}_heater"


def render_configuration(rooms: list[Room]) -> str:
    """The ``configuration.yaml``: the integrations IHP depends on and the simulated devices."""
    lines = [
        "homeassistant:",
        "  name: IHP e2e",
        f"  time_zone: {TIMEZONE}",
        "  unit_system: metric",
        "  latitude: 48.85",
        "  longitude: 2.35",
        "  elevation: 30",
        "http:",
        "recorder:",
        "history:",
        "onboarding:",
        "schedule:",
        "logger:",
        "  default: warning",
        "  logs:",
        "    custom_components.intelligent_heating_pilot: debug",
        "    custom_components.scheduler: info",
        "    custom_components.climate_scheduler: info",
        "input_boolean:",
        *[f"  {room.key}_heater:" for room in rooms],
        "input_number:",
        "  outdoor_temperature:",
        "    min: -30",
        "    max: 45",
        "    step: 0.1",
        "    initial: 5",
        *[
            f"  {room.key}_temperature:\n    min: 0\n    max: 40\n    step: 0.1\n    initial: 20"
            for room in rooms
        ],
    ]
    return "\n".join(lines) + "\n"


class HomeAssistantStack:
    """A Home Assistant container with a seeded configuration."""

    def __init__(self, workdir: Path, image: str = DEFAULT_IMAGE, name: str = "ihp-e2e") -> None:
        self.workdir = workdir
        self.image = image
        self.name = name
        self.config_dir = workdir / "config"
        self.port = 0
        self.token = ""

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # --- lifecycle ----------------------------------------------------------------------

    def prepare(
        self,
        rooms: list[Room],
        entries: list[Mapping[str, Any]],
        integrations: Mapping[str, Path],
    ) -> None:
        """Write the configuration, the seeded config entries and the custom components."""
        components = self.config_dir / "custom_components"
        components.mkdir(parents=True, exist_ok=True)
        for domain, source in integrations.items():
            shutil.copytree(source, components / domain, ignore=IGNORED_COPY, dirs_exist_ok=True)
        (self.config_dir / "configuration.yaml").write_text(render_configuration(rooms))
        storage = self.config_dir / ".storage"
        storage.mkdir(exist_ok=True)
        (storage / "core.config_entries").write_text(json.dumps(_entries_storage(entries)))

    def start(self) -> None:
        """Start the container and wait until Home Assistant answers."""
        self.port = _free_port()
        _docker(
            "run", "-d", "--name", self.name, "-p", f"127.0.0.1:{self.port}:{CONTAINER_PORT}",
            "-e", f"TZ={TIMEZONE}", "-v", f"{self.config_dir}:/config", self.image,
        )  # fmt: skip
        self.wait_until_ready()

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                if self._request("GET", "/api/onboarding", authorized=False) is not None:
                    return
            except (urllib.error.URLError, OSError, StackError):
                pass
            time.sleep(POLL_SECONDS)
        raise StackError(f"Home Assistant did not answer within {READY_TIMEOUT_SECONDS}s")

    def onboard(self) -> None:
        """Create the owner through the onboarding API and keep its access token."""
        auth = self._request(
            "POST",
            "/api/onboarding/users",
            {"client_id": CLIENT_ID, **USER},
            authorized=False,
        )
        form = f"grant_type=authorization_code&code={auth['auth_code']}&client_id={CLIENT_ID}"
        request = urllib.request.Request(
            f"{self.url}/auth/token",
            data=form.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            self.token = json.load(response)["access_token"]

    def restart(self) -> None:
        """Restart the container, as a user restarting Home Assistant would."""
        _docker("restart", self.name)
        self.wait_until_ready()

    def logs(self) -> str:
        return _docker("logs", self.name, check=False)

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, check=False)

    # --- Home Assistant APIs ------------------------------------------------------------

    def _request(self, method: str, path: str, body: Any = None, authorized: bool = True) -> Any:
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = response.read()
        except urllib.error.HTTPError as err:
            raise StackError(f"{method} {path}: {err.code} {err.read()[:300]!r}") from err
        return json.loads(payload) if payload else None

    def state(self, entity_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/api/states/{entity_id}")
        except StackError:
            return None

    def states(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/states")

    def call(self, domain: str, service: str, data: Mapping[str, Any] | None = None) -> Any:
        return self._request("POST", f"/api/services/{domain}/{service}", dict(data or {}))

    def config_entries(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/config/config_entries/entry")

    def websocket(self, message: Mapping[str, Any]) -> Any:
        """Send one WebSocket command and return its result."""
        return asyncio.run(self._websocket(message))

    async def _websocket(self, message: Mapping[str, Any]) -> Any:
        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(f"{self.url}/api/websocket") as socket,
        ):
            await socket.receive_json()
            await socket.send_json({"type": "auth", "access_token": self.token})
            await socket.receive_json()
            await socket.send_json({"id": 1, **message})
            reply = await socket.receive_json()
        if not reply.get("success"):
            raise StackError(f"WebSocket {message.get('type')}: {reply.get('error')}")
        return reply.get("result")

    def wait_for(
        self, condition: Callable[[], bool], timeout_seconds: float, describe: str
    ) -> None:
        """Poll until the condition holds; fail with a description when it does not."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(POLL_SECONDS)
        raise StackError(f"Timed out after {timeout_seconds:.0f}s waiting for {describe}")


def _entries_storage(entries: list[Mapping[str, Any]]) -> dict[str, Any]:
    from homeassistant.config_entries import STORAGE_VERSION, STORAGE_VERSION_MINOR

    return {
        "version": STORAGE_VERSION,
        "minor_version": STORAGE_VERSION_MINOR,
        "key": "core.config_entries",
        "data": {"entries": list(entries)},
    }


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=600
    )
    if check and result.returncode != 0:
        raise StackError(f"docker {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout + result.stderr


def utcnow() -> datetime:
    return datetime.now(UTC)
