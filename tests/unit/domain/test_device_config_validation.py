"""Regression tests for DeviceConfig lhs_retention_days=0 behavior.

Tests validating that lhs_retention_days=0 (no retention) is properly
supported in DeviceConfig, allowing users to disable data retention.

These are RED phase tests that validate the new behavior.
"""

from __future__ import annotations

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)


class TestDeviceConfigLhsRetentionDaysValidation:
    """Test suite for lhs_retention_days validation in DeviceConfig."""

    def test_device_config_with_zero_lhs_retention_days_is_valid(self) -> None:
        """Test that lhs_retention_days=0 (no retention) is allowed.

        REGRESSION TEST: This was previously rejected by validation.
        With lhs_retention_days=0, users can disable heating slope retention
        completely if they don't want historical data to affect anticipation.

        Expected: DeviceConfig should accept 0 without raising ValueError
        """
        device_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=0,  # No retention - should be allowed
        )

        assert device_config.lhs_retention_days == 0

    def test_device_config_with_negative_lhs_retention_days_is_invalid(self) -> None:
        """Test that lhs_retention_days=-1 (negative) is rejected.

        Negative values are invalid and should raise ValueError.
        Valid values are: 0 (no retention) or positive integers (with retention).
        """
        with pytest.raises(ValueError) as exc_info:
            DeviceConfig(
                device_id="test_device_1",
                vtherm_entity_id="climate.vtherm",
                scheduler_entities=["switch.schedule"],
                lhs_retention_days=-1,  # Invalid: negative
            )

        assert "lhs_retention_days" in str(exc_info.value).lower()

    def test_device_config_with_positive_lhs_retention_days_is_valid(self) -> None:
        """Test that positive lhs_retention_days values are allowed."""
        device_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=30,
        )

        assert device_config.lhs_retention_days == 30

    def test_device_config_default_lhs_retention_days(self) -> None:
        """Test that default lhs_retention_days is 30."""
        device_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
        )

        assert device_config.lhs_retention_days == 30

    def test_device_config_immutability_with_zero_lhs_retention_days(self) -> None:
        """Test that DeviceConfig with lhs_retention_days=0 is immutable."""
        device_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=0,
        )

        # Should raise AttributeError because dataclass is frozen
        with pytest.raises(AttributeError):
            device_config.lhs_retention_days = 30  # type: ignore[misc]

    def test_device_config_boundary_conditions(self) -> None:
        """Test boundary conditions for lhs_retention_days.

        Valid: 0 and all positive integers
        Invalid: negative integers
        """
        # Valid: 0
        valid_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=0,
        )
        assert valid_config.lhs_retention_days == 0

        # Valid: 1 (minimum positive)
        valid_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=1,
        )
        assert valid_config.lhs_retention_days == 1

        # Valid: large value
        valid_config = DeviceConfig(
            device_id="test_device_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.schedule"],
            lhs_retention_days=365,
        )
        assert valid_config.lhs_retention_days == 365

        # Invalid: negative
        with pytest.raises(ValueError):
            DeviceConfig(
                device_id="test_device_1",
                vtherm_entity_id="climate.vtherm",
                scheduler_entities=["switch.schedule"],
                lhs_retention_days=-1,
            )


class TestDeviceConfigSafetyShutoffGrace:
    """Validate that DeviceConfig correctly stores and validates safety_shutoff_grace_minutes.

    GREEN: The validation is already implemented in DeviceConfig.__post_init__.
    All tests in this class are expected to PASS with the current skeleton.
    """

    def test_default_safety_shutoff_grace_is_ten_minutes(self) -> None:
        """DeviceConfig default for safety_shutoff_grace_minutes is 10.

        Matches the HeatingCycleService default to ensure consistent behaviour
        out-of-the-box without explicit configuration.

        # PASSES with fix (default value set in dataclass)
        """
        config = DeviceConfig(
            device_id="dev_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
        )

        assert config.safety_shutoff_grace_minutes == 10

    def test_safety_shutoff_grace_zero_is_valid(self) -> None:
        """grace=0 disables grace period entirely — must be accepted without error.

        # PASSES with fix (validation: >= 0)
        """
        config = DeviceConfig(
            device_id="dev_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            safety_shutoff_grace_minutes=0,
        )

        assert config.safety_shutoff_grace_minutes == 0

    def test_safety_shutoff_grace_positive_value_is_stored_correctly(self) -> None:
        """Positive grace values are stored as-is.

        # PASSES with fix
        """
        config = DeviceConfig(
            device_id="dev_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            safety_shutoff_grace_minutes=15,
        )

        assert config.safety_shutoff_grace_minutes == 15

    def test_negative_safety_shutoff_grace_is_rejected(self) -> None:
        """Negative grace values are invalid and must raise ValueError.

        A negative grace period is nonsensical (cannot wait a negative duration).

        # PASSES with fix (validation raises ValueError for < 0)
        """
        with pytest.raises(ValueError) as exc_info:
            DeviceConfig(
                device_id="dev_1",
                vtherm_entity_id="climate.vtherm",
                scheduler_entities=[],
                safety_shutoff_grace_minutes=-1,
            )

        assert "safety_shutoff_grace" in str(exc_info.value).lower()

    def test_safety_shutoff_grace_immutability(self) -> None:
        """DeviceConfig is frozen — safety_shutoff_grace_minutes cannot be mutated.

        # PASSES with fix (frozen=True dataclass)
        """
        config = DeviceConfig(
            device_id="dev_1",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            safety_shutoff_grace_minutes=10,
        )

        with pytest.raises(AttributeError):
            config.safety_shutoff_grace_minutes = 0  # type: ignore[misc]
