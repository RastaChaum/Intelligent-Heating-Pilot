"""Tests for ML prediction service."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.services.ml_prediction_service import (
    MLPredictionService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    LaggedFeatures,
)


class TestMLPredictionService:
    """Test suite for MLPredictionService."""
    
    def test_predict_without_model_returns_none(self) -> None:
        """Test prediction without trained model returns None."""
        service = MLPredictionService()
        
        features = LaggedFeatures(
            current_temp=20.0,
            target_temp=22.0,
            temp_delta=2.0,
            temp_lag_15min=19.5,
            temp_lag_30min=19.0,
            temp_lag_60min=18.5,
            temp_lag_90min=18.0,
            power_lag_15min=0.0,
            power_lag_30min=0.0,
            power_lag_60min=0.0,
            power_lag_90min=0.0,
            outdoor_temp=10.0,
            humidity=50.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        result = service.predict_duration(features)
        
        assert result is None
    
    def test_train_and_predict_basic(self) -> None:
        """Test basic training and prediction workflow."""
        service = MLPredictionService()
        
        # Create training data
        X_train = [
            [20.0, 22.0, 2.0, 19.5, 19.0, 18.5, 18.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
            [18.0, 22.0, 4.0, 17.5, 17.0, 16.5, 16.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
            [19.0, 22.0, 3.0, 18.5, 18.0, 17.5, 17.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
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
        features = LaggedFeatures(
            current_temp=20.0,
            target_temp=22.0,
            temp_delta=2.0,
            temp_lag_15min=19.5,
            temp_lag_30min=19.0,
            temp_lag_60min=18.5,
            temp_lag_90min=18.0,
            power_lag_15min=0.0,
            power_lag_30min=0.0,
            power_lag_60min=0.0,
            power_lag_90min=0.0,
            outdoor_temp=10.0,
            humidity=50.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        duration = service.predict_duration(features)
        
        assert duration is not None
        assert duration > 0
        assert duration < 180  # Reasonable duration
    
    def test_train_with_insufficient_data(self) -> None:
        """Test training with insufficient data raises error."""
        service = MLPredictionService()
        
        # Only 1 sample (minimum is 3)
        X_train = [[20.0, 22.0, 2.0, 19.5, 19.0, 18.5, 18.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866]]
        y_train = [30.0]
        
        with pytest.raises(ValueError, match="At least 3 training examples"):
            service.train_model(X_train, y_train)
    
    def test_serialize_and_deserialize_model(self) -> None:
        """Test model serialization and deserialization."""
        service = MLPredictionService()
        
        # Train a model
        X_train = [
            [20.0, 22.0, 2.0, 19.5, 19.0, 18.5, 18.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
            [18.0, 22.0, 4.0, 17.5, 17.0, 16.5, 16.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
            [19.0, 22.0, 3.0, 18.5, 18.0, 17.5, 17.0, 0, 0, 0, 0, 10.0, 50.0, 0.5, 0.866],
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
        features = LaggedFeatures(
            current_temp=20.0,
            target_temp=22.0,
            temp_delta=2.0,
            temp_lag_15min=19.5,
            temp_lag_30min=19.0,
            temp_lag_60min=18.5,
            temp_lag_90min=18.0,
            power_lag_15min=0.0,
            power_lag_30min=0.0,
            power_lag_60min=0.0,
            power_lag_90min=0.0,
            outdoor_temp=10.0,
            humidity=50.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        duration = new_service.predict_duration(features)
        assert duration is not None
