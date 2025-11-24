"""ML-based prediction service using XGBoost."""
from __future__ import annotations

import logging
import pickle
from typing import Any

import numpy as np

from ..value_objects import CycleFeatures

_LOGGER = logging.getLogger(__name__)

# Import XGBoost only when needed to avoid dependency issues
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    _LOGGER.warning("XGBoost not available. ML predictions will not work.")
    XGBOOST_AVAILABLE = False


class MLPredictionService:
    """Service for ML-based heating duration prediction using XGBoost.
    
    This service contains pure domain logic for ML model training and prediction.
    It operates on preprocessed features and does not access infrastructure.
    """
    
    def __init__(self) -> None:
        """Initialize the ML prediction service."""
        self._model: Any = None
        self._is_trained = False
    
    def is_trained(self) -> bool:
        """Check if model is trained and ready for predictions.
        
        Returns:
            True if model is trained, False otherwise.
        """
        return self._is_trained and self._model is not None
    
    def train_model(
        self,
        X_train: list[list[float]],
        y_train: list[float],
        **kwargs: Any
    ) -> dict[str, float]:
        """Train an XGBoost model for heating duration prediction.
        
        Args:
            X_train: Training features (list of feature vectors)
            y_train: Training targets (optimal duration in minutes)
            **kwargs: Additional XGBoost parameters
            
        Returns:
            Dictionary with training metrics (e.g., RMSE).
            
        Raises:
            ValueError: If training data is insufficient or invalid.
            RuntimeError: If XGBoost is not available.
        """
        if not XGBOOST_AVAILABLE:
            raise RuntimeError("XGBoost is not installed. Cannot train model.")
        
        if len(X_train) < 3:
            raise ValueError("At least 3 training examples required for XGBoost training")
        
        if len(X_train) != len(y_train):
            raise ValueError("X_train and y_train must have same length")
        
        # Convert to numpy arrays
        X = np.array(X_train, dtype=np.float32)
        y = np.array(y_train, dtype=np.float32)
        
        # Default XGBoost parameters optimized for small datasets
        default_params = {
            "objective": "reg:squarederror",
            "max_depth": 4,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 2,
            "random_state": 42,
        }
        
        # Override with user params
        params = {**default_params, **kwargs}
        
        _LOGGER.info(
            "Training XGBoost model with %d samples and %d features",
            len(X_train),
            X.shape[1] if len(X.shape) > 1 else 1,
        )
        
        # Train the model
        self._model = xgb.XGBRegressor(**params)
        self._model.fit(X, y, verbose=False)
        self._is_trained = True
        
        # Calculate training metrics
        y_pred = self._model.predict(X)
        rmse = np.sqrt(np.mean((y - y_pred) ** 2))
        mae = np.mean(np.abs(y - y_pred))
        
        metrics = {
            "rmse": float(rmse),
            "mae": float(mae),
            "n_samples": len(X_train),
            "n_features": X.shape[1] if len(X.shape) > 1 else 1,
        }
        
        _LOGGER.info(
            "Model trained successfully. RMSE: %.2f min, MAE: %.2f min",
            rmse,
            mae,
        )
        
        return metrics
    
    def predict_duration(self, features: CycleFeatures) -> float | None:
        """Predict optimal heating duration given features.
        
        Args:
            features: CycleFeatures for prediction
            
        Returns:
            Predicted duration in minutes, or None if model not trained.
        """
        if not self.is_trained():
            _LOGGER.warning("Model not trained. Cannot make prediction.")
            return None
        
        # Convert features to array
        feature_dict = features.to_feature_dict()
        # Get feature names from the features object itself
        feature_names = features.get_feature_names()
        X = np.array([[feature_dict[name] for name in feature_names]], dtype=np.float32)
        
        # Make prediction
        prediction = self._model.predict(X)[0]
        
        # Ensure positive duration
        duration = max(0.0, float(prediction))
        
        _LOGGER.debug(
            "Predicted duration: %.1f minutes for temp_delta=%.1f°C",
            duration,
            features.temp_delta,
        )
        
        return duration
    
    def serialize_model(self) -> bytes | None:
        """Serialize the trained model to bytes using pickle.
        
        Returns:
            Serialized model bytes, or None if model not trained.
        """
        if not self.is_trained():
            _LOGGER.warning("Cannot serialize: model not trained")
            return None
        
        # Use pickle for serialization
        return pickle.dumps(self._model)
    
    def deserialize_model(self, model_bytes: bytes) -> None:
        """Deserialize and load a trained model from bytes.
        
        Args:
            model_bytes: Serialized model bytes
            
        Raises:
            RuntimeError: If XGBoost is not available.
        """
        if not XGBOOST_AVAILABLE:
            raise RuntimeError("XGBoost is not installed. Cannot load model.")
        
        # Use pickle for deserialization
        self._model = pickle.loads(model_bytes)
        self._is_trained = True
        
        _LOGGER.info("Model deserialized successfully")
    
    def get_feature_importance(self, feature_names: list[str] | None = None) -> dict[str, float] | None:
        """Get feature importance scores from the trained model.
        
        Args:
            feature_names: Optional list of feature names. If not provided,
                          uses CycleFeatures names by default.
        
        Returns:
            Dictionary mapping feature names to importance scores,
            or None if model not trained.
        """
        if not self.is_trained():
            return None
        
        importance_values = self._model.feature_importances_
        if feature_names is None:
            feature_names = CycleFeatures.get_feature_names()
        
        return {
            name: float(importance)
            for name, importance in zip(feature_names, importance_values)
        }
