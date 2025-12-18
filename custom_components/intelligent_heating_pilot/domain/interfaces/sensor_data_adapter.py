"""Sensor data adapter interface - now using generic IHistoricalDataAdapter.

This file is kept for backwards compatibility but should not be used directly.
Use IHistoricalDataAdapter instead.
"""
from __future__ import annotations

from .historical_data_adapter import IHistoricalDataAdapter

# Re-export for backwards compatibility
ISensorDataAdapter = IHistoricalDataAdapter
