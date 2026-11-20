"""Architecture tests: the domain stays free of Home Assistant and its ports stay abstract."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from custom_components.intelligent_heating_pilot import domain
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IClimateCommander,
    IPreheatActuator,
    IPreheatRecordStore,
    IPresetTemperatureResolver,
    ISchedulerOwnershipResolver,
    IWakeUpSourceReader,
)

DOMAIN_ROOT = Path(inspect.getfile(domain)).parent


def _imported_modules(source: str) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_the_domain_package_imports_no_home_assistant() -> None:
    offenders = [
        f"{path.relative_to(DOMAIN_ROOT)}: {module}"
        for path in DOMAIN_ROOT.rglob("*.py")
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if module == "homeassistant" or module.startswith("homeassistant.")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "port",
    [
        IPreheatActuator,
        ISchedulerOwnershipResolver,
        IClimateCommander,
        IPreheatRecordStore,
        IWakeUpSourceReader,
        IPresetTemperatureResolver,
    ],
)
def test_the_new_ports_are_abstract(port: type) -> None:
    with pytest.raises(TypeError):
        port()


def test_the_domain_does_not_import_the_package_level_const_module() -> None:
    """Defaults and setting keys live in domain/constants.py; const.py re-exports them (#302)."""
    offenders = [
        f"{path.relative_to(DOMAIN_ROOT)}: {module}"
        for path in DOMAIN_ROOT.rglob("*.py")
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if module.endswith(".const") or module.rsplit(".", 1)[-1] == "const"
    ]
    assert offenders == []
