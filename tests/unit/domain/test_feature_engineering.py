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
    
    def test_calculate_aggregated_lagged_values_avg(self) -> None:
        """Test aggregated lagged value calculation with average."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 5), 20.2),
            (datetime(2025, 1, 1, 6, 10), 20.4),
            (datetime(2025, 1, 1, 6, 15), 20.5),
            (datetime(2025, 1, 1, 6, 20), 20.7),
            (datetime(2025, 1, 1, 6, 25), 20.9),
            (datetime(2025, 1, 1, 6, 30), 21.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        
        result = self.service.calculate_aggregated_lagged_values(
            history, current_time, aggregation_func="avg"
        )
        
        # Check that we have values for all lag intervals
        assert 15 in result
        assert 30 in result
        assert result[15] is not None
        assert result[30] is not None
    
    def test_calculate_aggregated_lagged_values_empty(self) -> None:
        """Test aggregated lagged values with empty history."""
        history: list[tuple[datetime, float]] = []
        current_time = datetime(2025, 1, 1, 6, 30)
        
        result = self.service.calculate_aggregated_lagged_values(
            history, current_time, aggregation_func="avg"
        )
        
        # All values should be None
        assert all(v is None for v in result.values())
    
    def test_calculate_aggregated_lagged_values_min(self) -> None:
        """Test aggregated lagged values with min aggregation."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 10), 21.0),
            (datetime(2025, 1, 1, 6, 20), 19.0),
            (datetime(2025, 1, 1, 6, 30), 22.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        
        result = self.service.calculate_aggregated_lagged_values(
            history, current_time, aggregation_func="min"
        )
        
        # Values between 6:15-6:30 (15 min lag): 19.0, 22.0 -> min=19.0
        assert result[15] == 19.0
    
    def test_calculate_aggregated_lagged_values_max(self) -> None:
        """Test aggregated lagged values with max aggregation."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 10), 21.0),
            (datetime(2025, 1, 1, 6, 20), 19.0),
            (datetime(2025, 1, 1, 6, 30), 22.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        
        result = self.service.calculate_aggregated_lagged_values(
            history, current_time, aggregation_func="max"
        )
        
        # Values between 6:15-6:30 (15 min lag): 19.0, 22.0 -> max=22.0
        assert result[15] == 22.0
    
    def test_calculate_aggregated_lagged_values_median(self) -> None:
        """Test aggregated lagged values with median aggregation."""
        history = [
            (datetime(2025, 1, 1, 6, 0), 20.0),
            (datetime(2025, 1, 1, 6, 5), 20.0),
            (datetime(2025, 1, 1, 6, 10), 21.0),
            (datetime(2025, 1, 1, 6, 15), 21.0),
            (datetime(2025, 1, 1, 6, 20), 22.0),
            (datetime(2025, 1, 1, 6, 25), 22.0),
            (datetime(2025, 1, 1, 6, 30), 23.0),
        ]
        current_time = datetime(2025, 1, 1, 6, 30)
        
        result = self.service.calculate_aggregated_lagged_values(
            history, current_time, aggregation_func="median"
        )
        
        # Check that median is calculated
        assert result[15] is not None
