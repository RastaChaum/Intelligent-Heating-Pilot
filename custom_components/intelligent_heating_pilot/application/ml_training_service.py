"""Application service for ML model training orchestration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ..domain.interfaces import IHistoricalDataReader, IMLModelStorage
from ..domain.services import (
    CycleLabelingService,
    FeatureEngineeringService,
    MLPredictionService,
)
from ..domain.value_objects import CycleFeatures, TrainingExample

_LOGGER = logging.getLogger(__name__)


class MLTrainingApplicationService:
    """Application service for training and managing ML models.
    
    This service orchestrates the complete training pipeline:
    1. Extract historical heating cycles from database
    2. Extract features from cycle start data only (no lagged features)
    3. Label cycles with optimal durations
    4. Train XGBoost model
    5. Persist trained model
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
        climate_entity_id: str,
        weather_entity_id: str,
        humidity_entity_id: str,
        lookback_months: int = 6,
        min_cycles: int = 10,
    ) -> dict[str, Any]:
        """Train an ML model for a specific room using historical data.
        
        Args:
            climate_entity_id: Identifier for the room/climate entity
            weather_entity_id: Identifier for the weather entity
            humidity_entity_id: Identifier for the humidity entity
            lookback_months: How many months of historical data to use
            min_cycles: Minimum number of heating cycles required for training
            
        Returns:
            Dictionary with training results and metrics.
            
        Raises:
            ValueError: If insufficient data for training.
        """
        _LOGGER.info(
            "Starting ML model training for room %s (lookback: %d months)",
            climate_entity_id,
            weather_entity_id,
            humidity_entity_id,
            lookback_months,
        )
        
        # Step 1: Extract historical heating cycles
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_months * 30)
        
        cycles = await self._historical_reader.get_heating_cycles(
            climate_entity_id=climate_entity_id,
            start_date=start_date,
            end_date=end_date,
            humidity_entity_id=humidity_entity_id,
            outdoor_temp_entity_id=weather_entity_id,
            outdoor_humidity_entity_id=weather_entity_id,  # Often same entity provides temp and humidity
            cloud_coverage_entity_id=weather_entity_id,
        )
        
        _LOGGER.info("Extracted %d heating cycles from database", len(cycles))
        
        # Step 2: Filter valid cycles for training
        valid_cycles = []
        for cycle in cycles:
            power_history = await self._historical_reader.get_radiator_power_history(
                climate_entity_id=cycle.climate_entity_id,
                start_time=cycle.cycle_start,
                end_time=cycle.cycle_end,
            )
            if power_history:
                avg_power = sum(power for ts, power in power_history) / len(power_history)
            else:
                avg_power = 50.0  # Default power if no history available
                
            if self._cycle_labeler.is_cycle_valid_for_training(cycle, avg_power=avg_power):
                valid_cycles.append(cycle)
        
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
        
        # Step 3: Create training dataset with feature engineering
        training_examples = []
        
        for cycle in valid_cycles:
            # Calculate optimal label (Y target)
            optimal_duration = self._cycle_labeler.label_heating_cycle(cycle)
            
            # Step 3a: Create features from cycle start data only
            try:
                # Extract features available at cycle start (no lagged features)
                cycle_features = self._feature_engineer.create_cycle_features(cycle)
                
                # Step 3b: Create training example
                example = TrainingExample(
                    features=cycle_features,
                    target_duration_minutes=optimal_duration,
                    cycle_id=cycle.cycle_id,
                )
                
                training_examples.append(example)
                
                _LOGGER.debug(
                    "Created training example for cycle %s: optimal=%.1f min, "
                    "temp_delta=%.1f°C",
                    cycle.cycle_id,
                    optimal_duration,
                    cycle_features.temp_delta,
                )
            except Exception as e:
                _LOGGER.warning(
                    "Failed to create features for cycle %s: %s. Skipping.",
                    cycle.cycle_id,
                    str(e),
                )
                continue
        
        if not training_examples:
            raise ValueError(
                "No training examples created after feature engineering. "
                "This may indicate insufficient historical data."
            )
        
        _LOGGER.info(
            "Created %d training examples with features from %d valid cycles",
            len(training_examples),
            len(valid_cycles),
        )
        
        # Step 4: Train the ML model
        # Convert training examples to X and y arrays
        X_train = [
            example.features.to_feature_dict()
            for example in training_examples
        ]
        y_train = [
            example.target_duration_minutes
            for example in training_examples
        ]
        
        # Convert feature dicts to flat arrays for XGBoost
        # CycleFeatures contains scalar float attributes available at cycle start
        feature_names = training_examples[0].features.get_feature_names()
        X_train_arrays = [
            [float(feature_dict[name]) if feature_dict[name] is not None else 0.0 
             for name in feature_names]
            for feature_dict in X_train
        ]
        
        _LOGGER.info(
            "Training XGBoost model with %d examples and %d features",
            len(X_train_arrays),
            len(feature_names),
        )
        
        # Train the model
        metrics = self._ml_service.train_model(
            X_train=X_train_arrays,
            y_train=y_train,
        )
        
        _LOGGER.info(
            "Model training complete. RMSE: %.2f min, MAE: %.2f min",
            metrics["rmse"],
            metrics["mae"],
        )
        
        # Step 5: Persist the trained model
        model_bytes = self._ml_service.serialize_model()
        if model_bytes:
            await self._model_storage.save_model(
                climate_entity_id=climate_entity_id,
                model_data=model_bytes,
                metadata={
                    "trained_at": datetime.now().isoformat(),
                    "n_samples": len(training_examples),
                    "n_features": len(feature_names),
                    "rmse": metrics["rmse"],
                    "mae": metrics["mae"],
                    "lookback_months": lookback_months,
                },
            )
            _LOGGER.info("Model persisted successfully for room %s", climate_entity_id)
        
        return {
            "status": "training_complete",
            "cycles_extracted": len(cycles),
            "cycles_valid": len(valid_cycles),
            "training_examples": len(training_examples),
            "rmse": metrics["rmse"],
            "mae": metrics["mae"],
            "n_features": len(feature_names),
        }
    
    async def retrain_model_with_new_data(
        self,
        climate_entity_id: str,
        weather_entity_id: str,
        humidity_entity_id: str,
    ) -> dict[str, Any]:
        """Retrain model using both historical data and new collected examples.
        
        This implements the continuous learning loop:
        1. Load existing model
        2. Get new training examples since last training
        3. Combine with historical data
        4. Retrain model
        5. Persist updated model
        
        Args:
            climate_entity_id: Identifier for the climate entity
            weather_entity_id: Identifier for the weather entity
            humidity_entity_id: Identifier for the humidity entity
            
        Returns:
            Dictionary with retraining results and metrics.
        """
        _LOGGER.info("Starting model retraining for room %s", climate_entity_id)
        
        # Check if model exists
        if not await self._model_storage.model_exists(climate_entity_id):
            _LOGGER.warning("No existing model found, performing initial training")
            return await self.train_model_for_room(climate_entity_id=climate_entity_id, weather_entity_id=weather_entity_id, humidity_entity_id=humidity_entity_id)
        
        # Get metadata to find last training time
        metadata = await self._model_storage.get_model_metadata(climate_entity_id)
        last_training = metadata.get("trained_at") if metadata else None
        
        since_time = None
        if last_training:
            since_time = datetime.fromisoformat(last_training)
        
        # Get new examples
        new_examples = await self._model_storage.get_new_training_examples(
            climate_entity_id=climate_entity_id,
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
