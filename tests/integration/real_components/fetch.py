"""Download the pinned third-party Home Assistant components the real-component tests load.

Why: the scheduler and thermostat integrations IHP talks to are never installed in the other
tests, so a change in their attributes or services would pass the suite and break in production.
Each release is pinned by tag *and* sha256, so a moved tag or a tampered archive fails loudly.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

COMPONENTS_FILE = Path(__file__).with_name("components.json")
# Named like a real config directory: Home Assistant recognises a custom component's code by
# "custom_components" appearing in its file path, and behaves differently otherwise.
CACHE_DIR = Path(__file__).parents[3] / ".cache" / "real_components" / "custom_components"
DOWNLOAD_TIMEOUT_SECONDS = 60
_ARCHIVE_URL = "https://github.com/{repository}/archive/refs/tags/{tag}.tar.gz"


class ComponentFetchError(RuntimeError):
    """The pinned archive could not be downloaded or does not match its checksum."""


def _download(repository: str, tag: str, sha256: str) -> bytes:
    url = _ARCHIVE_URL.format(repository=repository, tag=tag)
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload: bytes = response.read()
    except OSError as err:
        raise ComponentFetchError(f"Cannot download {url}: {err}") from err
    actual = hashlib.sha256(payload).hexdigest()
    if actual != sha256:
        raise ComponentFetchError(f"{url} has sha256 {actual}, expected {sha256}")
    return payload


def _extract(payload: bytes, domain: str, destination: Path) -> None:
    """Keep only ``custom_components/<domain>`` of the archive, at ``destination/<domain>``."""
    prefix = f"custom_components/{domain}/"
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            _, _, relative = member.name.partition("/")
            if not relative.startswith(prefix) or not member.isfile():
                continue
            target = destination / domain / relative[len(prefix) :]
            if destination.resolve() not in target.resolve().parents:
                raise ComponentFetchError(f"Unsafe path in archive: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is not None:
                target.write_bytes(extracted.read())


def fetch_components() -> Path:
    """Make every pinned component available and return the directory holding them.

    The directory is meant to be added to the ``custom_components`` search path. A component
    already fetched at its pinned tag and checksum is not downloaded again.
    """
    pins: dict[str, dict[str, str]] = json.loads(COMPONENTS_FILE.read_text())
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for domain, pin in pins.items():
        marker = CACHE_DIR / domain / ".pin"
        wanted = f"{pin['tag']} {pin['sha256']}"
        if marker.exists() and marker.read_text() == wanted:
            continue
        payload = _download(pin["repository"], pin["tag"], pin["sha256"])
        _extract(payload, domain, CACHE_DIR)
        marker.write_text(wanted)
    return CACHE_DIR
