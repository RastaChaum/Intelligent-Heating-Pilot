"""Tests for feature engineering service."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.feature_engineering_service import (
    FeatureEngineeringService,
)


class TestFeatureEngineeringService:
    """Test suite for FeatureEngineeringService."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = FeatureEngineeringService()
    
    def test_calculate_time_of_day_features_midnight(self) -> None:
        """Test cyclic time encoding at midnight."""
        timestamp = datetime(2025, 1, 1, 0, 0)
        
        hour_sin, hour_cos = self.service.calculate_time_of_day_features(timestamp)
        
        # At hour 0, sin should be ~0 and cos should be ~1
        assert abs(hour_sin) < 0.01
        assert abs(hour_cos - 1.0) < 0.01
    
    def test_calculate_time_of_day_features_noon(self) -> None:
        """Test cyclic time encoding at noon."""
        timestamp = datetime(2025, 1, 1, 12, 0)
        
        hour_sin, hour_cos = self.service.calculate_time_of_day_features(timestamp)
        
        # At hour 12, sin should be ~0 and cos should be ~-1
        assert abs(hour_sin) < 0.01
        assert abs(hour_cos - (-1.0)) < 0.01
    
    def test_calculate_time_of_day_features_6am(self) -> None:
        """Test cyclic time encoding at 6am."""
        timestamp = datetime(2025, 1, 1, 6, 0)
        
        hour_sin, hour_cos = self.service.calculate_time_of_day_features(timestamp)
        
        # At hour 6, sin should be ~1 and cos should be ~0
        assert abs(hour_sin - 1.0) < 0.01
        assert abs(hour_cos) < 0.01
    
    def test_calculate_lagged_value_exact_match(self) -> None:
        """Test lagged value calculation with exact timestamp match."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 15), 20.5),
            (datetime(2025, 1, 1, 6, 30), 21.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 15
        
        value = self.service.calculate_lagged_value(history, current_time, lag_minutes)
        
        assert value == pytest.approx(20.5, abs=0.01)
    
    def test_calculate_lagged_value_interpolation(self) -> None:
        """Test lagged value with linear interpolation."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 30), 21.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 15
        
        # Should interpolate between 20.0 and 21.0 at 6:15
        value = self.service.calculate_lagged_value(history, current_time, lag_minutes)
        
        assert value == pytest.approx(20.5, abs=0.01)
    
    def test_calculate_lagged_value_not_enough_history(self) -> None:
        """Test lagged value when history doesn't go back far enough."""
        history = [
            (datetime(2025, 1, 1, 6, 20), 20.5),
            (datetime(2025, 1, 1, 6, 30), 21.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 30
        
        # Lag goes back to 6:00, but history only starts at 6:20
        value = self.service.calculate_lagged_value(history, current_time, lag_minutes)
        
        assert value is None
    
    def test_calculate_lagged_value_empty_history(self) -> None:
        """Test lagged value with empty history."""
        history: list[tuple[datetime, float]] = []
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 15
        
        value = self.service.calculate_lagged_value(history, current_time, lag_minutes)
        
        assert value is None
    
    def test_calculate_power_lagged_value(self) -> None:
        """Test power state lagged value calculation."""
        power_history = [
            (datetime(2025, 1, 1, 6, 0), False),
            (datetime(2025, 1, 1, 6, 10), True),
            (datetime(2025, 1, 1, 6, 30), True),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 20
        
        # At 6:10 (20 min ago), power was True
        value = self.service.calculate_power_lagged_value(
            power_history, current_time, lag_minutes
        )
        
        assert value == pytest.approx(1.0, abs=0.01)
    
    def test_calculate_power_lagged_value_off(self) -> None:
        """Test power state lagged value when off."""
        power_history = [
            (datetime(2025, 1, 1, 6, 0), False),
            (datetime(2025, 1, 1, 6, 30), False),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        lag_minutes = 15
        
        value = self.service.calculate_power_lagged_value(
            power_history, current_time, lag_minutes
        )
        
        assert value == pytest.approx(0.0, abs=0.01)
