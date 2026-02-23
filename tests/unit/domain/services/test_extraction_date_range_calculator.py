"""Tests for ExtractionDateRangeCalculator service."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from custom_components.intelligent_heating_pilot.domain.services.extraction_date_range_calculator import (
    ExtractionDateRangeCalculator,
)


class TestExtractionDateRangeCalculatorBasic:
    """Test basic date range calculation."""

    def test_calculate_range_with_empty_cache(self) -> None:
        """Test range calculation when cache is empty (oldest_cycle_in_cache=None).

        Expected behavior:
        - Extract full retention window: (now - retention_days) to today
        """
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90
        oldest_cycle_in_cache = None

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle_in_cache,
            current_time=current_time,
        )

        # THEN
        expected_start = date(2023, 10, 17)  # 2024-01-15 minus 90 days
        expected_end = date(2024, 1, 15)
        assert start_date == expected_start
        assert end_date == expected_end

    def test_calculate_range_with_cache_existing(self) -> None:
        """Test range calculation when cache has data.

        Expected behavior:
        - Extract from (oldest_cycle - 24h) to today
        - Respect retention boundary (don't extract before oldest allowed date)
        """
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90

        # Oldest cycle is 20 days ago
        oldest_cycle_in_cache = datetime(2024, 1, 5, 8, 30, 0)
        oldest_minus_24h = date(2024, 1, 4)  # One day before oldest

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle_in_cache,
            current_time=current_time,
        )

        # THEN
        # Should extract from oldest_minus_24h since it's after retention boundary
        assert start_date == oldest_minus_24h
        assert end_date == date(2024, 1, 15)

    def test_calculate_range_respects_retention_boundary(self) -> None:
        """Test that extraction never goes before retention boundary.

        When oldest_cycle is very old, should cap at retention boundary.
        """
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90
        retention_boundary = date(2023, 10, 17)

        # Oldest cycle is 100 days ago (before retention boundary)
        oldest_cycle_in_cache = datetime(2023, 10, 7, 8, 30, 0)

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle_in_cache,
            current_time=current_time,
        )

        # THEN
        # Should use retention boundary, not oldest_minus_24h (which is before boundary)
        assert start_date == retention_boundary
        assert end_date == date(2024, 1, 15)


class TestExtractionDateRangeCalculatorEdgeCases:
    """Test edge cases in date range calculation."""

    def test_calculate_range_with_very_recent_cycles(self) -> None:
        """Test when oldest cycle is very recent (less than 24h old)."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90

        # Oldest cycle is 1 hour old
        oldest_cycle_in_cache = datetime(2024, 1, 15, 11, 0, 0)

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle_in_cache,
            current_time=current_time,
        )

        # THEN
        # Should still extract from oldest - 24h (yesterday)
        assert start_date == date(2024, 1, 14)
        assert end_date == date(2024, 1, 15)

    def test_calculate_range_at_midnight_boundary(self) -> None:
        """Test date range calculation right at date boundaries."""
        # GIVEN: Time exactly at midnight
        current_time = datetime(2024, 1, 15, 0, 0, 0)
        retention_days = 90

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        expected_start = date(2023, 10, 17)
        expected_end = date(2024, 1, 15)
        assert start_date == expected_start
        assert end_date == expected_end

    def test_calculate_range_with_zero_retention_days(self) -> None:
        """Test behavior with 0 retention days (extract only today)."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 0

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        # When retention_days=0, boundary is current_time itself
        assert start_date == date(2024, 1, 15)
        assert end_date == date(2024, 1, 15)

    def test_calculate_range_with_single_day_retention(self) -> None:
        """Test with minimal retention window (1 day)."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 1

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        assert start_date == date(2024, 1, 14)
        assert end_date == date(2024, 1, 15)

    def test_calculate_range_returns_date_objects_not_datetime(self) -> None:
        """Test that returned range uses date objects, not datetime."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 30, 45)
        retention_days = 7

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        assert isinstance(start_date, date)
        assert isinstance(end_date, date)
        assert not isinstance(start_date, datetime)
        assert not isinstance(end_date, datetime)


class TestExtractionDateRangeCalculatorRefresh:
    """Test 24-hour refresh range calculation."""

    def test_calculate_refresh_range_default_time(self) -> None:
        """Test refresh range with default current_time."""
        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_refresh_range()

        # THEN
        today = date.today()
        yesterday = today - timedelta(days=1)
        assert start_date == yesterday
        assert end_date == today

    def test_calculate_refresh_range_specific_time(self) -> None:
        """Test refresh range with specific current_time."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 14, 30, 0)

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_refresh_range(
            current_time=current_time
        )

        # THEN
        assert start_date == date(2024, 1, 14)
        assert end_date == date(2024, 1, 15)

    def test_calculate_refresh_range_always_spans_two_days(self) -> None:
        """Test that refresh range always includes yesterday and today."""
        # GIVEN: Different times within the same day
        times = [
            datetime(2024, 1, 15, 0, 0, 0),  # midnight
            datetime(2024, 1, 15, 12, 0, 0),  # noon
            datetime(2024, 1, 15, 23, 59, 59),  # end of day
        ]

        # WHEN/THEN
        for current_time in times:
            start_date, end_date = ExtractionDateRangeCalculator.calculate_refresh_range(
                current_time=current_time
            )

            # All should give yesterday and today
            assert start_date == date(2024, 1, 14)
            assert end_date == date(2024, 1, 15)

    def test_calculate_refresh_range_returns_date_objects(self) -> None:
        """Test that refresh range returns date objects."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 30, 45)

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_refresh_range(
            current_time=current_time
        )

        # THEN
        assert isinstance(start_date, date)
        assert isinstance(end_date, date)
        assert not isinstance(start_date, datetime)
        assert not isinstance(end_date, datetime)


class TestExtractionDateRangeCalculatorRetentionBehavior:
    """Test retention window behavior."""

    def test_extraction_respects_90_day_retention(self) -> None:
        """Test that 90-day retention is respected."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        # Calculate expected start date
        boundary_datetime = current_time - timedelta(days=retention_days)
        expected_start = boundary_datetime.date()

        assert start_date == expected_start
        # Verify the span is exactly 90 days (inclusive)
        day_count = (end_date - start_date).days + 1  # +1 for inclusive range
        assert day_count == 91  # 90 days + today

    def test_extraction_respects_custom_retention(self) -> None:
        """Test that custom retention windows are respected."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 30

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        expected_start = date(2023, 12, 16)  # 30 days before Jan 15
        assert start_date == expected_start
        assert end_date == date(2024, 1, 15)

    def test_oldest_cycle_before_retention_boundary(self) -> None:
        """Test when oldest cycle is older than retention boundary."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90
        retention_boundary = date(2023, 10, 17)

        # Oldest cycle is 6 months old (way before retention boundary)
        oldest_cycle_in_cache = datetime(2023, 7, 15, 10, 0, 0)

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle_in_cache,
            current_time=current_time,
        )

        # THEN
        # Must respect retention boundary, not oldest_minus_24h
        assert start_date == retention_boundary
        assert end_date == date(2024, 1, 15)


class TestExtractionDateRangeCalculatorCrossMonthBoundaries:
    """Test date range calculation across month boundaries."""

    def test_range_spans_january_to_february(self) -> None:
        """Test range calculation crossing month boundary."""
        # GIVEN
        current_time = datetime(2024, 2, 5, 12, 0, 0)
        retention_days = 30

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        assert start_date == date(2024, 1, 6)
        assert end_date == date(2024, 2, 5)

    def test_range_spans_year_boundary(self) -> None:
        """Test range calculation crossing year boundary."""
        # GIVEN
        current_time = datetime(2024, 1, 10, 12, 0, 0)
        retention_days = 30

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        assert start_date == date(2023, 12, 11)
        assert end_date == date(2024, 1, 10)


class TestExtractionDateRangeCalculatorInputValidation:
    """Test input validation and error handling."""

    def test_calculate_range_with_negative_retention_days_treated_as_current(self) -> None:
        """Test behavior with negative retention days.

        Note: Current implementation doesn't validate negative, but it should
        be handled gracefully. Negative days would create a future boundary.
        """
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = -5  # Invalid, but test behavior

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN
        # With negative days, boundary becomes future date
        # The implemented behavior will create a future boundary
        expected_start = date(2024, 1, 20)  # 5 days in future
        assert start_date == expected_start


class TestExtractionDateRangeCalculatorTimezoneAwareness:
    """Test timezone handling in date range calculation."""

    def test_datetime_without_timezone_info(self) -> None:
        """Test with naive datetime (no timezone)."""
        # GIVEN: Naive datetime (common in tests)
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 7

        # WHEN
        start_date, end_date = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=None,
            current_time=current_time,
        )

        # THEN: Should work without raising timezone errors
        assert start_date == date(2024, 1, 8)
        assert end_date == date(2024, 1, 15)

    def test_calculation_consistency_with_naive_datetimes(self) -> None:
        """Test that multiple calls with same input give consistent results."""
        # GIVEN
        current_time = datetime(2024, 1, 15, 12, 0, 0)
        retention_days = 90
        oldest_cycle = datetime(2024, 1, 1, 8, 0, 0)

        # WHEN: Call multiple times
        result1 = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle,
            current_time=current_time,
        )
        result2 = ExtractionDateRangeCalculator.calculate_extraction_range(
            retention_days=retention_days,
            oldest_cycle_in_cache=oldest_cycle,
            current_time=current_time,
        )

        # THEN: Results should be identical
        assert result1 == result2
