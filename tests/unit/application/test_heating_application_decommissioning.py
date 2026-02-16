"""Unit tests verifying HeatingApplication uses Orchestrator, not HeatingApplicationService directly.

This is a DECOMMISSIONING VERIFICATION test:
- RED phase: HeatingApplication still calls HeatingApplicationService methods directly
- GREEN phase (after refactoring): All calls go through HeatingOrchestrator → use cases

Tests verify that complex workflows are delegated to orchestrator, not handled by service.
"""

from __future__ import annotations

import inspect

from custom_components.intelligent_heating_pilot.heating_application import HeatingApplication


class TestHeatingApplicationDecommissioning:
    """Verify HeatingApplication never calls HeatingApplicationService directly."""

    def test_heating_application_has_orchestrator_attribute(self) -> None:
        """Test: HeatingApplication should have _orchestrator attribute wiring.

        RED: Currently missing `_orchestrator` attribute in __init__
        GREEN: Should initialize `_orchestrator` in __init__ or async_load
        """
        # Check that HeatingApplication.__init__() mentions _orchestrator
        source = inspect.getsource(HeatingApplication.__init__)

        assert (
            "_orchestrator" in source
        ), "HeatingApplication should initialize _orchestrator attribute"

    def test_async_update_delegates_to_orchestrator_not_service(self) -> None:
        """Test: async_update() should call orchestrator, not service directly.

        RED: Currently calls self._app_service.calculate_and_schedule_anticipation()
        GREEN: Should call self._orchestrator.calculate_and_schedule_anticipation()
        """
        # Read the async_update method source
        source = inspect.getsource(HeatingApplication.async_update)

        # RED PHASE: This will FAIL because service is still being called
        # The assertion checks for the OLD pattern (direct service call)
        if "self._app_service.calculate_and_schedule_anticipation" in source:
            assert False, (
                "async_update should NOT call self._app_service.calculate_and_schedule_anticipation() "
                "directly — must use self._orchestrator instead"
            )

        # GREEN PHASE: Should call orchestrator instead
        assert (
            "self._orchestrator" in source
        ), "async_update should delegate to self._orchestrator"

    def test_heating_application_service_class_has_removed_workflow_methods(
        self,
    ) -> None:
        """Test: HeatingApplicationService should NOT have complex workflow methods.

        RED: Service still has these methods
        GREEN: These methods are removed from service
        """
        from custom_components.intelligent_heating_pilot.application import (
            HeatingApplicationService,
        )

        # Service should NOT have these workflow methods
        forbidden_methods = [
            "calculate_and_schedule_anticipation",
            "_schedule_anticipation",
            "check_overshoot_risk",
        ]

        for method_name in forbidden_methods:
            # RED PHASE: These methods still exist on service (test FAILS)
            # GREEN PHASE: These methods are removed (test PASSES)
            has_method = hasattr(HeatingApplicationService, method_name)

            if has_method:
                pytest.fail(
                    f"HeatingApplicationService should NOT have {method_name}() — "
                    f"it must be removed and delegated to orchestrator use cases"
                )

    def test_heating_application_service_still_has_lifecycle_methods(self) -> None:
        """Test: HeatingApplicationService should still expose lifecycle methods.

        These methods are needed for DI container wiring.
        """
        from custom_components.intelligent_heating_pilot.application import (
            HeatingApplicationService,
        )

        # These should still exist on service (for lifecycle setup)
        required_methods = [
            "get_heating_cycle_service",
            "get_global_lhs_calculator",
            "get_contextual_lhs_calculator",
            "set_heating_cycle_lifecycle_manager",
            "set_lhs_lifecycle_manager",
            "reset_learned_slopes",
        ]

        for method_name in required_methods:
            assert hasattr(
                HeatingApplicationService, method_name
            ), f"Service should keep {method_name}() for lifecycle management"

    def test_orchestrator_class_exists_and_has_workflow_methods(self) -> None:
        """Test: Orchestrator class exists and has required workflow methods.

        RED: Orchestrator might be missing or incomplete
        GREEN: Orchestrator fully implements all workflows
        """
        from custom_components.intelligent_heating_pilot.application.orchestrator import (
            HeatingOrchestrator,
        )

        # These are the workflows that MUST be on Orchestrator
        required_methods = [
            "calculate_and_schedule_anticipation",  # Main workflow (moved from service)
            "calculate_anticipation_only",  # Pure calculation
            "enable_preheating",  # Start heating (aka trigger anticipation)
            "disable_preheating",  # Stop heating
            "cancel_preheating",  # Cancel scheduled
            "reset_all_learning_data",  # Reset slopes
            "is_preheating_active",  # State query
        ]

        for method_name in required_methods:
            assert hasattr(
                HeatingOrchestrator, method_name
            ), f"HeatingOrchestrator must have {method_name}() — this workflow was moved from service"

    def test_device_config_used_not_config_entry(self) -> None:
        """Test: HeatingApplication uses injected DeviceConfig, not config_entry.

        This ensures DDD principle: application layer doesn't depend on HA ConfigEntry.
        """
        source = inspect.getsource(HeatingApplication.__init__)

        # Should accept DeviceConfig as parameter
        assert "device_config: DeviceConfig" in source, (
            "HeatingApplication.__init__ should accept device_config parameter"
        )

        # Should NOT read from config_entry in __init__
        assert (
            "config_entry" not in source or "self._config_entry: ConfigEntry | None = None" in source
        ), "HeatingApplication should not read from config_entry in __init__, only store it later"
