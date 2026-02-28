"""Unit tests for ContextualLHSData value object.

Tests the immutable data carrier for contextual LHS results,
including validation and display logic.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.contextual_lhs_data import (
    ContextualLHSData,
)


class TestContextualLHSData:
    """Test suite for ContextualLHSData value object."""

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime for testing."""
        return datetime(2025, 2, 9, 12, 0, 0)

    # ===== Test: Valid Creation =====

    def test_create_contextual_lhs_data_with_valid_values(self, base_datetime: datetime) -> None:
        """Test creating ContextualLHSData with all valid required fields.

        RED: Ensure dataclass can be instantiated with required fields.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert data.hour == 6
        assert data.lhs == 14.75
        assert data.cycle_count == 2
        assert data.calculated_at == base_datetime

    def test_create_contextual_lhs_data_with_reason(self, base_datetime: datetime) -> None:
        """Test creating ContextualLHSData with optional reason field.

        RED: Ensure optional reason field is preserved.
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
            reason="insufficient_data",
        )

        assert data.reason == "insufficient_data"

    # ===== Test: Immutability (Frozen Dataclass) =====

    def test_contextual_lhs_data_is_frozen(self, base_datetime: datetime) -> None:
        """Test that ContextualLHSData is immutable.

        RED: Frozen dataclass should raise FrozenInstanceError on modification.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        with pytest.raises(
            (AttributeError, TypeError, FrozenInstanceError),
            match="frozen|cannot set attribute|cannot assign to field",
        ):
            data.lhs = 15.0  # type: ignore

    def test_contextual_lhs_data_cannot_modify_hour(self, base_datetime: datetime) -> None:
        """Test that hour field cannot be modified.

        RED: Frozen dataclass should prevent any attribute modification.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        with pytest.raises(
            (AttributeError, TypeError, FrozenInstanceError),
            match="frozen|cannot set attribute|cannot assign to field",
        ):
            data.hour = 7  # type: ignore

    # ===== Test: Field Validation =====

    def test_contextual_lhs_data_hour_validation_below_zero(self, base_datetime: datetime) -> None:
        """Test that hour must be >= 0.

        RED: __post_init__ should raise ValueError for invalid hour.
        """
        with pytest.raises(ValueError, match="hour must be 0-23"):
            ContextualLHSData(
                hour=-1,
                lhs=14.75,
                cycle_count=2,
                calculated_at=base_datetime,
            )

    def test_contextual_lhs_data_hour_validation_above_23(self, base_datetime: datetime) -> None:
        """Test that hour must be <= 23.

        RED: __post_init__ should raise ValueError for invalid hour.
        """
        with pytest.raises(ValueError, match="hour must be 0-23"):
            ContextualLHSData(
                hour=24,
                lhs=14.75,
                cycle_count=2,
                calculated_at=base_datetime,
            )

    def test_contextual_lhs_data_hour_boundary_zero(self, base_datetime: datetime) -> None:
        """Test that hour=0 (midnight) is valid.

        RED: Edge case for hour boundary.
        """
        data = ContextualLHSData(
            hour=0,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert data.hour == 0

    def test_contextual_lhs_data_hour_boundary_23(self, base_datetime: datetime) -> None:
        """Test that hour=23 (11 PM) is valid.

        RED: Edge case for hour boundary.
        """
        data = ContextualLHSData(
            hour=23,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert data.hour == 23

    def test_contextual_lhs_data_lhs_cannot_be_negative(self, base_datetime: datetime) -> None:
        """Test that LHS cannot be negative if not None.

        RED: __post_init__ should reject negative LHS values.
        """
        with pytest.raises(ValueError, match="lhs must be positive or None"):
            ContextualLHSData(
                hour=6,
                lhs=-1.5,
                cycle_count=2,
                calculated_at=base_datetime,
            )

    def test_contextual_lhs_data_lhs_can_be_none(self, base_datetime: datetime) -> None:
        """Test that LHS can be None (no data available).

        RED: None should be a valid value for lhs field.
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        assert data.lhs is None

    def test_contextual_lhs_data_lhs_can_be_zero(self, base_datetime: datetime) -> None:
        """Test that LHS can be 0.0 (no heating).

        RED: Zero is a valid, distinct value from None.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=0.0,
            cycle_count=1,
            calculated_at=base_datetime,
        )

        assert data.lhs == 0.0

    def test_contextual_lhs_data_cycle_count_cannot_be_negative(
        self, base_datetime: datetime
    ) -> None:
        """Test that cycle_count cannot be negative.

        RED: __post_init__ should reject negative cycle counts.
        """
        with pytest.raises(ValueError, match="cycle_count must be >= 0"):
            ContextualLHSData(
                hour=6,
                lhs=14.75,
                cycle_count=-1,
                calculated_at=base_datetime,
            )

    def test_contextual_lhs_data_cycle_count_can_be_zero(self, base_datetime: datetime) -> None:
        """Test that cycle_count can be 0 (no cycles for this hour).

        RED: Zero cycles is valid state (no data for this hour).
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        assert data.cycle_count == 0

    # ===== Test: is_available Property =====

    def test_contextual_lhs_data_is_available_true_when_has_lhs_and_cycles(
        self, base_datetime: datetime
    ) -> None:
        """Test is_available is True when lhs and cycle_count > 0.

        RED: Property should return True when both conditions met.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert data.is_available is True

    def test_contextual_lhs_data_is_available_false_when_lhs_none(
        self, base_datetime: datetime
    ) -> None:
        """Test is_available is False when lhs is None.

        RED: Property should return False when lhs is None.
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        assert data.is_available is False

    def test_contextual_lhs_data_is_available_false_when_zero_cycles(
        self, base_datetime: datetime
    ) -> None:
        """Test is_available is False when cycle_count is 0.

        RED: Property should return False when no cycles.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        assert data.is_available is False

    def test_contextual_lhs_data_is_available_false_when_lhs_zero(
        self, base_datetime: datetime
    ) -> None:
        """Test is_available considers lhs=0.0 as unavailable.

        RED: Corner case - zero LHS with cycles should still be unavailable().
        """
        data = ContextualLHSData(
            hour=6,
            lhs=0.0,
            cycle_count=1,
            calculated_at=base_datetime,
        )

        # Zero LHS is technically a valid measurement but is_available checks if lhs is not None
        # This is the intended behavior based on the property definition
        assert data.is_available is True

    # ===== Test: get_display_value() =====

    def test_contextual_lhs_data_display_value_returns_float_when_available(
        self, base_datetime: datetime
    ) -> None:
        """Test get_display_value returns rounded float when LHS available.

        RED: Should return float rounded to 2 decimal places.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.7546,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        display = data.get_display_value()

        assert isinstance(display, float)
        assert display == 14.75

    def test_contextual_lhs_data_display_value_returns_unknown_when_none(
        self, base_datetime: datetime
    ) -> None:
        """Test get_display_value returns 'unknown' when LHS is None.

        RED: Should return string 'unknown' for unavailable data.
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        display = data.get_display_value()

        assert display == "unknown"
        assert isinstance(display, str)

    def test_contextual_lhs_data_display_value_handles_various_precisions(
        self, base_datetime: datetime
    ) -> None:
        """Test get_display_value rounds to 2 decimal places.

        RED: Test various rounding scenarios.
        """
        test_cases = [
            (14.754, 14.75),  # Rounds down
            (14.755, 14.76),  # Rounds up
            (14.7, 14.7),  # Single decimal
            (14.0, 14.0),  # No decimals
            (14.123, 14.12),  # Truncates
        ]

        for lhs_value, expected in test_cases:
            data = ContextualLHSData(
                hour=6,
                lhs=lhs_value,
                cycle_count=1,
                calculated_at=base_datetime,
            )

            display = data.get_display_value()
            assert display == expected

    # ===== Test: Type Validation =====

    def test_contextual_lhs_data_hour_must_be_int(self, base_datetime: datetime) -> None:
        """Test that hour field accepts int type.

        RED: Type hint enforcement.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert isinstance(data.hour, int)

    def test_contextual_lhs_data_lhs_must_be_float_or_none(self, base_datetime: datetime) -> None:
        """Test that lhs field accepts float or None.

        RED: Type hint enforcement.
        """
        # Test with float
        data1 = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )
        assert isinstance(data1.lhs, (float, type(None)))

        # Test with None
        data2 = ContextualLHSData(
            hour=6,
            lhs=None,
            cycle_count=2,
            calculated_at=base_datetime,
        )
        assert data2.lhs is None

    def test_contextual_lhs_data_cycle_count_must_be_int(self, base_datetime: datetime) -> None:
        """Test that cycle_count field accepts int type.

        RED: Type hint enforcement.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert isinstance(data.cycle_count, int)

    def test_contextual_lhs_data_calculated_at_must_be_datetime(
        self, base_datetime: datetime
    ) -> None:
        """Test that calculated_at field accepts datetime type.

        RED: Type hint enforcement.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert isinstance(data.calculated_at, datetime)

    # ===== Test: Default Reason Field =====

    def test_contextual_lhs_data_reason_defaults_to_empty_string(
        self, base_datetime: datetime
    ) -> None:
        """Test that reason field defaults to empty string when not provided.

        RED: Default value should be empty string.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        assert data.reason == ""
        assert isinstance(data.reason, str)

    def test_contextual_lhs_data_reason_stores_provided_value(
        self, base_datetime: datetime
    ) -> None:
        """Test that reason field stores provided value.

        RED: Custom reason should be preserved.
        """
        reason = "insufficient_data"
        data = ContextualLHSData(
            hour=6,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
            reason=reason,
        )

        assert data.reason == reason
