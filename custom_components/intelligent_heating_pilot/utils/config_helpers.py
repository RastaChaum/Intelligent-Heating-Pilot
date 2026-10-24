"""Configuration helper utilities."""

from __future__ import annotations

from typing import Any


def as_bool(value: Any, default: bool = False) -> bool:
    """Normalize truthy/falsy values to a strict boolean.

    Important for stringified options (e.g. "False" should yield False).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default
