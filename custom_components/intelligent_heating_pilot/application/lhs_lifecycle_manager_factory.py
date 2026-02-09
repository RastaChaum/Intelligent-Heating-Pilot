"""Factory for LhsLifecycleManager - wires dependencies with DDD compliance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .lhs_lifecycle_manager import LhsLifecycleManager

if TYPE_CHECKING:
    from ..domain.interfaces import IModelStorage, ITimerScheduler
    from ..domain.services.contextual_lhs_calculator_service import ContextualLHSCalculatorService
    from ..domain.services.global_lhs_calculator_service import GlobalLHSCalculatorService

_LOGGER = logging.getLogger(__name__)


class LhsLifecycleManagerFactory:
    """Factory for creating LhsLifecycleManager with singleton pattern.

    Singleton Pattern:
    - **One instance per device_id**: Each IHP device gets its own manager instance
    - **Shared across requests**: Multiple calls with same device_id return same instance
    - **Thread-safe**: Factory maintains internal registry to track instances

    Note on device_id:
    Since LhsLifecycleManager doesn't directly hold device_id, the singleton key
    is derived from the model_storage instance (assuming one storage per device).
    For proper device-level isolation, ensure each device has its own IModelStorage.

    Dependency Wiring:
    - Injects all required dependencies (calculators, storage, scheduler)
    - Ensures DDD compliance (domain services, infrastructure adapters)

    Usage:
    ```python
    # First call creates instance
    manager1 = factory.create(storage, global_calc, contextual_calc, ...)

    # Second call with same storage returns same instance
    manager2 = factory.create(storage, global_calc, contextual_calc, ...)
    assert manager1 is manager2  # True
    ```
    """

    # Class-level registry: storage_id -> LhsLifecycleManager instance
    # Using id(model_storage) as key since LHS manager doesn't have device_id directly
    _instances: dict[int, LhsLifecycleManager] = {}

    @classmethod
    def create(
        cls,
        model_storage: IModelStorage,
        global_lhs_calculator: GlobalLHSCalculatorService,
        contextual_lhs_calculator: ContextualLHSCalculatorService,
        timer_scheduler: ITimerScheduler | None = None,
    ) -> LhsLifecycleManager:
        """Create or return existing LhsLifecycleManager for model_storage.

        Singleton Behavior:
        - Uses id(model_storage) as singleton key (assumes one storage per device)
        - If instance exists for this storage, returns existing instance
        - If no instance exists, creates new one and stores in registry
        - Registry is class-level, shared across all factory instances

        Dependency Injection:
        - model_storage: Infrastructure adapter for persistent LHS storage
        - global_lhs_calculator: Domain service for computing global LHS from cycles
        - contextual_lhs_calculator: Domain service for computing contextual LHS by hour
        - timer_scheduler: Infrastructure adapter for scheduling 24h refresh

        Args:
            model_storage: Persistent storage adapter for cached LHS values.
            global_lhs_calculator: Service for computing global LHS.
            contextual_lhs_calculator: Service for computing contextual LHS by hour.
            timer_scheduler: Optional scheduler for periodic 24h refresh.

        Returns:
            Singleton LhsLifecycleManager instance for the model_storage.
        """
        storage_id = id(model_storage)

        # Check if instance already exists
        if storage_id in cls._instances:
            _LOGGER.debug("Returning existing LhsLifecycleManager for storage_id=%s", storage_id)
            return cls._instances[storage_id]

        # Create new instance
        _LOGGER.debug("Creating new LhsLifecycleManager for storage_id=%s", storage_id)

        manager = LhsLifecycleManager(
            model_storage=model_storage,
            global_lhs_calculator=global_lhs_calculator,
            contextual_lhs_calculator=contextual_lhs_calculator,
            timer_scheduler=timer_scheduler,
        )

        # Store in registry
        cls._instances[storage_id] = manager
        _LOGGER.debug("Registered LhsLifecycleManager for storage_id=%s", storage_id)

        return manager

    @classmethod
    def reset_instances(cls) -> None:
        """Clear singleton registry (for testing only).

        Use Case:
        Called in test teardown to ensure clean state between tests.
        Should NOT be used in production code.
        """
        cls._instances = {}
        _LOGGER.debug("Reset LhsLifecycleManager singleton registry")
