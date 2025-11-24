"""ML-based prediction service using XGBoost with sklearn fallback."""
from __future__ import annotations

import logging
import pickle
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from ..value_objects import CycleFeatures

_LOGGER = logging.getLogger(__name__)

# Import XGBoost only when needed to avoid dependency issues
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
    _LOGGER.info("XGBoost is available and will be used for ML predictions")
except ImportError:
    XGBOOST_AVAILABLE = False
    _LOGGER.warning(
        "XGBoost not available. Falling back to sklearn's HistGradientBoostingRegressor. "
        "This is expected on Alpine-based systems."
    )


class MLPredictionService:
    """Service for ML-based heating duration prediction using XGBoost or sklearn fallback.
    
    This service contains pure domain logic for ML model training and prediction.
    It operates on preprocessed features and does not access infrastructure.
    
    Uses XGBoost when available, otherwise falls back to sklearn's HistGradientBoostingRegressor.
    """
    
    def __init__(self) -> None:
        """Initialize the ML prediction service."""
        self._model: Any = None
        self._is_trained = False
        self._model_type: str = "xgboost" if XGBOOST_AVAILABLE else "sklearn"
    
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
        """Train a gradient boosting model for heating duration prediction.
        
        Uses XGBoost when available, otherwise falls back to sklearn's 
        HistGradientBoostingRegressor.
        
        Args:
            X_train: Training features (list of feature vectors)
            y_train: Training targets (optimal duration in minutes)
            **kwargs: Additional model parameters (XGBoost or sklearn specific)
            
        Returns:
            Dictionary with training metrics (e.g., RMSE).
            
        Raises:
            ValueError: If training data is insufficient or invalid.
        """
        if len(X_train) < 3:
            raise ValueError("At least 3 training examples required for model training")
        
        if len(X_train) != len(y_train):
            raise ValueError("X_train and y_train must have same length")
        
        # Convert to numpy arrays
        X = np.array(X_train, dtype=np.float32)
        y = np.array(y_train, dtype=np.float32)
        
        if XGBOOST_AVAILABLE:
            # Use XGBoost when available
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
            params = {**default_params, **kwargs}
            
            _LOGGER.info(
                "Training XGBoost model with %d samples and %d features",
                len(X_train),
                X.shape[1] if len(X.shape) > 1 else 1,
            )
            
            self._model = xgb.XGBRegressor(**params)
            self._model.fit(X, y, verbose=False)
            self._model_type = "xgboost"
        else:
            # Fallback to sklearn's HistGradientBoostingRegressor
            # Map similar parameters to sklearn equivalents
            default_params = {
                "max_depth": 4,
                "learning_rate": 0.1,
                "max_iter": 100,  # Equivalent to n_estimators
                "min_samples_leaf": 2,  # Similar to min_child_weight
                "random_state": 42,
            }
            # Filter kwargs to only include valid sklearn parameters
            valid_sklearn_params = {
                "max_depth", "learning_rate", "max_iter", "min_samples_leaf", 
                "random_state", "max_leaf_nodes", "l2_regularization"
            }
            sklearn_kwargs = {k: v for k, v in kwargs.items() if k in valid_sklearn_params}
            params = {**default_params, **sklearn_kwargs}
            
            _LOGGER.info(
                "Training sklearn HistGradientBoostingRegressor model with %d samples and %d features",
                len(X_train),
                X.shape[1] if len(X.shape) > 1 else 1,
            )
            
            self._model = HistGradientBoostingRegressor(**params)
            self._model.fit(X, y)
            self._model_type = "sklearn"
        
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
            "model_type": self._model_type,
        }
        
        _LOGGER.info(
            "Model (%s) trained successfully. RMSE: %.2f min, MAE: %.2f min",
            self._model_type,
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
        
        Stores both the model and its type to enable correct deserialization.
        
        Returns:
            Serialized model bytes, or None if model not trained.
        """
        if not self.is_trained():
            _LOGGER.warning("Cannot serialize: model not trained")
            return None
        
        # Serialize model with type information for proper deserialization
        model_data = {
            "model": self._model,
            "model_type": self._model_type,
        }
        return pickle.dumps(model_data)
    
    def deserialize_model(self, model_bytes: bytes) -> None:
        """Deserialize and load a trained model from bytes.
        
        Handles both XGBoost and sklearn models. If a model was trained with XGBoost
        but XGBoost is not available, the deserialization will fail with an appropriate error.
        
        Args:
            model_bytes: Serialized model bytes
            
        Raises:
            RuntimeError: If the model type requires XGBoost but it's not available.
            pickle.UnpicklingError: If deserialization fails.
        """
        try:
            # Try to load as new format (with model_type)
            model_data = pickle.loads(model_bytes)
            
            if isinstance(model_data, dict) and "model_type" in model_data:
                # New format with type information
                self._model = model_data["model"]
                self._model_type = model_data["model_type"]
                
                # Check if we can use this model
                if self._model_type == "xgboost" and not XGBOOST_AVAILABLE:
                    raise RuntimeError(
                        "Cannot load XGBoost model: XGBoost is not installed. "
                        "Please retrain the model with sklearn fallback."
                    )
                
                _LOGGER.info("Model deserialized successfully (type: %s)", self._model_type)
            else:
                # Legacy format - assume it's an XGBoost model
                if not XGBOOST_AVAILABLE:
                    raise RuntimeError(
                        "Cannot load legacy model: XGBoost is not installed. "
                        "Please retrain the model."
                    )
                self._model = model_data
                self._model_type = "xgboost"
                _LOGGER.info("Legacy model deserialized successfully (assumed XGBoost)")
            
            self._is_trained = True
            
        except Exception as e:
            _LOGGER.error("Failed to deserialize model: %s", str(e))
            raise
    
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
