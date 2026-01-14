"""Strategy factory for creating decision strategies."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..domain.interfaces import ISchedulerReader, IModelStorage
from ..domain.interfaces.decision_strategy import IDecisionStrategy
from ..domain.services.simple_decision_strategy import SimpleDecisionStrategy
from ..domain.services.ml_decision_strategy import MLDecisionStrategy
from ..const import DECISION_MODE_SIMPLE, DECISION_MODE_ML

_LOGGER = logging.getLogger(__name__)


class DecisionStrategyFactory:
    """Factory for creating decision strategies based on configuration.
    
    This factory belongs in the infrastructure layer as it deals with
    Home Assistant configuration and instantiation of concrete strategy
    implementations.
    
    The factory pattern ensures:
    - Single point of strategy creation
    - Easy testing with mocks
    - Configuration-driven behavior
    - No Home Assistant coupling in domain layer
    """
    
    @staticmethod
    def create_strategy(
        mode: str,
        scheduler_reader: ISchedulerReader,
        model_storage: IModelStorage,
        # hass: HomeAssistant,  # TODO: Add when implementing ML client
    ) -> IDecisionStrategy:
        """Create the appropriate decision strategy based on mode.
        
        Args:
            mode: Decision mode ('simple' or 'ml')
            scheduler_reader: Scheduler reader implementation
            model_storage: Model storage implementation
            # hass: Home Assistant instance (for ML API client)
            
        Returns:
            Configured decision strategy implementation
            
        Raises:
            ValueError: If mode is not recognized
        """
        _LOGGER.debug(f"Creating decision strategy for mode: {mode}")
        
        if mode == DECISION_MODE_SIMPLE:
            _LOGGER.debug("Instantiating SimpleDecisionStrategy")
            return SimpleDecisionStrategy(
                scheduler_reader=scheduler_reader,
                model_storage=model_storage,
            )
        
        elif mode == DECISION_MODE_ML:
            _LOGGER.debug("Instantiating MLDecisionStrategy")
            
            # TODO: Create ML client adapter when implementing
            # ml_client = MLApiAdapter(hass)
            
            return MLDecisionStrategy(
                scheduler_reader=scheduler_reader,
                # ml_client=ml_client,
            )
        
        else:
            error_msg = (
                f"Unknown decision mode: {mode}. "
                f"Valid modes: {DECISION_MODE_SIMPLE}, {DECISION_MODE_ML}"
            )
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)
