"""Extraction date range calculator for historical data loading."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class ExtractionDateRangeCalculator:
    """Utility service to calculate the date range for recording extraction.

    This service encapsulates the business logic for determining which dates should
    be extracted from the Recorder based on:
    - The configured retention period (in days)
    - The oldest cycle already in the cache
    - The current datetime

    The goal is to extract enough historical data to build machine learning models
    while respecting the retention window and avoiding redundant extraction.
    """

    @staticmethod
    def calculate_extraction_range(
        retention_days: int,
        oldest_cycle_in_cache: datetime | None,
        current_time: datetime | None = None,
    ) -> tuple[date, date]:
        """Calculate the date range for recording extraction.

        Logic:
        1. If oldest_cycle_in_cache is None (empty cache):
           - Extract from (now - retention_days) to today
        2. If oldest_cycle_in_cache exists:
           - Calculate: oldest_cycle - 24 hours
           - Extract from max(original_start_date, oldest_cycle - 24h) to today
           - This ensures we have one full day of context before the oldest cycle

        Args:
            retention_days: The retention window in days (e.g., 90)
            oldest_cycle_in_cache: The datetime of the oldest cycle currently in cache,
                                  or None if cache is empty
            current_time: Current datetime (for testing; defaults to now())

        Returns:
            A tuple of (start_date, end_date) both inclusive, both as datetime.date objects
        """
        if current_time is None:
            current_time = datetime.now()

        # Fixed boundary: start of retention window
        retention_boundary = current_time - timedelta(days=retention_days)

        if oldest_cycle_in_cache is None:
            # Empty cache: extract full retention window
            start_date = retention_boundary.date()
            end_date = current_time.date()
            _LOGGER.debug(
                "Empty cache: extracting from %s to %s (retention=%d days)",
                start_date,
                end_date,
                retention_days,
            )
            return start_date, end_date

        # Cache has data: look one day before the oldest cycle
        oldest_minus_24h = oldest_cycle_in_cache - timedelta(days=1)

        # Don't extract before retention boundary
        extraction_start = max(oldest_minus_24h, retention_boundary)
        extraction_start_date = extraction_start.date()
        extraction_end_date = current_time.date()

        _LOGGER.debug(
            "Cache has data (oldest=%s): extracting from %s to %s "
            "(retention_boundary=%s, oldest_minus_24h=%s)",
            oldest_cycle_in_cache.isoformat(),
            extraction_start_date,
            extraction_end_date,
            retention_boundary.date(),
            oldest_minus_24h.date(),
        )

        return extraction_start_date, extraction_end_date

    @staticmethod
    def calculate_refresh_range(
        current_time: datetime | None = None,
    ) -> tuple[date, date]:
        """Calculate the date range for a 24h refresh (last day only).

        This is used for periodic refresh to get the most recent data without
        re-extracting the entire history.

        Args:
            current_time: Current datetime (for testing; defaults to now())

        Returns:
            A tuple of (yesterday_date, today_date) as datetime.date objects
        """
        if current_time is None:
            current_time = datetime.now()

        yesterday = (current_time - timedelta(days=1)).date()
        today = current_time.date()

        _LOGGER.debug("24h refresh: extracting from %s to %s", yesterday, today)
        return yesterday, today
