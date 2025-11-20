"""Application service for ML model training orchestration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..domain.interfaces import IHistoricalDataReader, IMLModelStorage
from ..domain.services import (
    CycleLabelingService,
    FeatureEngineeringService,
    MLPredictionService,
)
from ..domain.value_objects import HeatingCycle, TrainingDataset, TrainingExample

_LOGGER = logging.getLogger(__name__)


class MLTrainingApplicationService:
    """Application service for training and managing ML models.
    
    This service orchestrates the complete training pipeline:
    1. Extract historical data from database
    2. Reconstruct heating cycles
    3. Engineer features with lagged values
    4. Label cycles with optimal durations
    5. Train XGBoost model
    6. Persist trained model
    """
    
    def __init__(
        self,
        historical_reader: IHistoricalDataReader,
        model_storage: IMLModelStorage,
    ) -> None:
        """Initialize the training service.
        
        Args:
            historical_reader: Adapter for reading historical data
            model_storage: Adapter for persisting trained models
        """
        self._historical_reader = historical_reader
        self._model_storage = model_storage
        
        # Domain services
        self._cycle_labeler = CycleLabelingService()
        self._feature_engineer = FeatureEngineeringService()
        self._ml_service = MLPredictionService()
    
    async def train_model_for_room(
        self,
        room_id: str,
        lookback_months: int = 6,
        min_cycles: int = 10,
    ) -> dict[str, any]:
        """Train an ML model for a specific room using historical data.
        
        Args:
            room_id: Identifier for the room/climate entity
            lookback_months: How many months of historical data to use
            min_cycles: Minimum number of heating cycles required for training
            
        Returns:
            Dictionary with training results and metrics.
            
        Raises:
            ValueError: If insufficient data for training.
        """
        _LOGGER.info(
            "Starting ML model training for room %s (lookback: %d months)",
            room_id,
            lookback_months,
        )
        
        # Step 1: Extract historical heating cycles
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_months * 30)
        
        cycles = await self._historical_reader.get_heating_cycles(
            room_id=room_id,
            start_date=start_date,
            end_date=end_date,
        )
        
        _LOGGER.info("Extracted %d heating cycles from database", len(cycles))
        
        # Step 2: Filter valid cycles for training
        valid_cycles = [
            cycle for cycle in cycles
            if self._cycle_labeler.is_cycle_valid_for_training(cycle)
        ]
        
        _LOGGER.info(
            "Filtered to %d valid cycles (removed %d invalid)",
            len(valid_cycles),
            len(cycles) - len(valid_cycles),
        )
        
        if len(valid_cycles) < min_cycles:
            raise ValueError(
                f"Insufficient training data: {len(valid_cycles)} cycles "
                f"(minimum: {min_cycles})"
            )
        
        # Step 3: Create training dataset
        # Note: Feature engineering would need temperature/power history
        # For now, we'll use a simplified approach
        training_examples = []
        
        for cycle in valid_cycles:
            # Calculate optimal label
            optimal_duration = self._cycle_labeler.label_heating_cycle(cycle)
            
            # In a full implementation, we would:
            # 1. Get temperature history around cycle start
            # 2. Get power history
            # 3. Create lagged features
            # For now, we'll skip this and just document the pattern
            
            # TODO: Implement full feature engineering pipeline
            _LOGGER.debug(
                "Cycle %s labeled with optimal duration: %.1f min",
                cycle.cycle_id,
                optimal_duration,
            )
        
        # Step 4: Train the model
        # This is a simplified example - full implementation would use actual features
        _LOGGER.warning(
            "Full feature engineering not yet implemented. "
            "Training would happen here with extracted features."
        )
        
        # Step 5: Persist the model
        # await self._model_storage.save_model(...)
        
        return {
            "status": "training_pipeline_defined",
            "cycles_extracted": len(cycles),
            "cycles_valid": len(valid_cycles),
            "note": "Full implementation requires historical data reader implementation",
        }
    
    async def retrain_model_with_new_data(
        self,
        room_id: str,
    ) -> dict[str, any]:
        """Retrain model using both historical data and new collected examples.
        
        This implements the continuous learning loop:
        1. Load existing model
        2. Get new training examples since last training
        3. Combine with historical data
        4. Retrain model
        5. Persist updated model
        
        Args:
            room_id: Identifier for the room
            
        Returns:
            Dictionary with retraining results and metrics.
        """
        _LOGGER.info("Starting model retraining for room %s", room_id)
        
        # Check if model exists
        if not await self._model_storage.model_exists(room_id):
            _LOGGER.warning("No existing model found, performing initial training")
            return await self.train_model_for_room(room_id)
        
        # Get metadata to find last training time
        metadata = await self._model_storage.get_model_metadata(room_id)
        last_training = metadata.get("trained_at") if metadata else None
        
        since_time = None
        if last_training:
            since_time = datetime.fromisoformat(last_training)
        
        # Get new examples
        new_examples = await self._model_storage.get_new_training_examples(
            room_id=room_id,
            since=since_time,
        )
        
        _LOGGER.info("Found %d new training examples since last training", len(new_examples))
        
        if len(new_examples) < 5:
            _LOGGER.info("Not enough new examples for retraining (need at least 5)")
            return {
                "status": "skipped",
                "reason": "insufficient_new_data",
                "new_examples": len(new_examples),
            }
        
        # TODO: Implement full retraining pipeline
        # 1. Load existing model
        # 2. Prepare new training data
        # 3. Combine with subset of historical data
        # 4. Retrain
        # 5. Evaluate improvements
        # 6. Save if better
        
        return {
            "status": "retraining_pipeline_defined",
            "new_examples": len(new_examples),
            "note": "Full implementation pending",
        }
