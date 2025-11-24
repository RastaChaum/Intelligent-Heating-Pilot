"""Tests for ML prediction service."""
from __future__ import annotations

import pickle

import pytest

from custom_components.intelligent_heating_pilot.domain.services.ml_prediction_service import (
    MLPredictionService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CycleFeatures,
)


def create_test_features(
    current_temp: float = 20.0,
    target_temp: float = 22.0,
) -> CycleFeatures:
    """Helper to create test CycleFeatures with all required fields."""
    return CycleFeatures(
        current_temp=current_temp,
        target_temp=target_temp,
        temp_delta=target_temp - current_temp,
        current_slope=0.5,
        outdoor_temp=10.0,
        outdoor_humidity=75.0,
        humidity=50.0,
        cloud_coverage=60.0,
    )


class TestMLPredictionService:
    """Test suite for MLPredictionService."""
    
    def test_predict_without_model_returns_none(self) -> None:
        """Test prediction without trained model returns None."""
        service = MLPredictionService()
        
        features = create_test_features()
        
        result = service.predict_duration(features)
        
        assert result is None
    
    def test_train_and_predict_basic(self) -> None:
        """Test basic training and prediction workflow."""
        service = MLPredictionService()
        
        # Create training data - now with extended features (41 features total)
        # Use the helper to get full feature dict
        
        X_train = [
            list(create_test_features(20.0, 22.0).to_feature_dict().values()),
            list(create_test_features(18.0, 22.0).to_feature_dict().values()),
            list(create_test_features(19.0, 22.0).to_feature_dict().values()),
        ]
        y_train = [30.0, 60.0, 45.0]  # Duration in minutes
        
        # Train the model
        metrics = service.train_model(X_train, y_train)
        
        # Check that model is trained
        assert service.is_trained()
        assert metrics is not None
        assert "rmse" in metrics
        assert metrics["rmse"] >= 0
        
        # Test prediction
        features = create_test_features()
        
        duration = service.predict_duration(features)
        
        assert duration is not None
        assert duration > 0
        assert duration < 180  # Reasonable duration
    
    def test_train_with_insufficient_data(self) -> None:
        """Test training with insufficient data raises error."""
        service = MLPredictionService()
        
        # Only 1 sample (minimum is 3)
        X_train = [list(create_test_features().to_feature_dict().values())]
        y_train = [30.0]
        
        with pytest.raises(ValueError, match="At least 3 training examples"):
            service.train_model(X_train, y_train)
    
    def test_serialize_and_deserialize_model(self) -> None:
        """Test model serialization and deserialization."""
        service = MLPredictionService()
        
        # Train a model
        X_train = [
            list(create_test_features(20.0, 22.0).to_feature_dict().values()),
            list(create_test_features(18.0, 22.0).to_feature_dict().values()),
            list(create_test_features(19.0, 22.0).to_feature_dict().values()),
        ]
        y_train = [30.0, 60.0, 45.0]
        
        service.train_model(X_train, y_train)
        
        # Serialize
        model_bytes = service.serialize_model()
        assert model_bytes is not None
        assert len(model_bytes) > 0
        
        # Create new service and deserialize
        new_service = MLPredictionService()
        assert not new_service.is_trained()
        
        new_service.deserialize_model(model_bytes)
        assert new_service.is_trained()
        
        # Test prediction works with deserialized model
        features = create_test_features()
        
        duration = new_service.predict_duration(features)
        assert duration is not None
    
    def test_model_type_tracking(self) -> None:
        """Test that model type is tracked correctly."""
        service = MLPredictionService()
        
        # Create training data
        X_train = [
            list(create_test_features(20.0, 22.0).to_feature_dict().values()),
            list(create_test_features(18.0, 22.0).to_feature_dict().values()),
            list(create_test_features(19.0, 22.0).to_feature_dict().values()),
        ]
        y_train = [30.0, 60.0, 45.0]
        
        # Train the model
        metrics = service.train_model(X_train, y_train)
        
        # Check that model type is reported in metrics
        assert "model_type" in metrics
        assert metrics["model_type"] in ["xgboost", "sklearn"]
        
        # Verify model type attribute is set
        assert service._model_type in ["xgboost", "sklearn"]
    
    def test_serialization_includes_model_type(self) -> None:
        """Test that serialized models include type information."""
        service = MLPredictionService()
        
        # Train a model
        X_train = [
            list(create_test_features(20.0, 22.0).to_feature_dict().values()),
            list(create_test_features(18.0, 22.0).to_feature_dict().values()),
            list(create_test_features(19.0, 22.0).to_feature_dict().values()),
        ]
        y_train = [30.0, 60.0, 45.0]
        
        service.train_model(X_train, y_train)
        
        # Serialize and check structure
        model_bytes = service.serialize_model()
        assert model_bytes is not None
        
        # Verify the serialized data contains model_type
        model_data = pickle.loads(model_bytes)
        assert isinstance(model_data, dict)
        assert "model" in model_data
        assert "model_type" in model_data
        assert model_data["model_type"] in ["xgboost", "sklearn"]
