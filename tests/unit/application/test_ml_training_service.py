"""Tests for ML training application service."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.intelligent_heating_pilot.application.ml_training_service import (
    MLTrainingApplicationService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HeatingCycle,
)


class TestMLTrainingApplicationService:
    """Test suite for MLTrainingApplicationService."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Mock dependencies
        self.historical_reader = AsyncMock()
        self.model_storage = AsyncMock()
        
        # Configure model_storage mock to return slopes history with default values
        # This needs to be a coroutine since get_room_slopes_history is async
        # Return some historical slopes to provide realistic learning features
        async def get_slopes_history(*args, **kwargs):
            # Return list of historical slopes (°C per minute)
            # These represent learned heating rates from past cycles
            return [0.05, 0.048, 0.052, 0.049, 0.051]
        
        self.model_storage.get_room_slopes_history.side_effect = get_slopes_history
        
        # Create service
        self.service = MLTrainingApplicationService(
            historical_reader=self.historical_reader,
            model_storage=self.model_storage,
        )
    
    def _create_test_cycle(
        self,
        cycle_id: str,
        climate_entity_id: str = "test_room",
        heating_started_at: datetime | None = None,
        target_reached_at: datetime | None = None,
        initial_temp: float = 18.0,
        target_temp: float = 21.0,
        final_temp: float = 21.0,
        actual_duration_minutes: float = 60.0,
        optimal_duration_minutes: float = 55.0,
        error_minutes: float = 5.0,
        initial_slope: float = 0.5,
        final_slope: float = 0.05,
        initial_humidity: float = 50.0,
        final_humidity: float = 45.0,
        initial_outdoor_temp: float = 5.0,
        final_outdoor_temp: float = 7.0,
        initial_outdoor_humidity: float = 80.0,
        final_outdoor_humidity: float = 75.0,
        initial_cloud_coverage: float = 50.0,
        final_cloud_coverage: float = 30.0,
    ) -> HeatingCycle:
        """Create a test heating cycle."""
        if heating_started_at is None:
            heating_started_at = datetime(2024, 1, 15, 6, 0, 0)
        if target_reached_at is None:
            target_reached_at = heating_started_at + timedelta(
                minutes=actual_duration_minutes + error_minutes
            )
        
        target_time = heating_started_at + timedelta(minutes=actual_duration_minutes)
        cycle_end = target_reached_at
        
        return HeatingCycle(
            initial_slope=initial_slope,
            cycle_id=cycle_id,
            climate_entity_id=climate_entity_id,
            cycle_start=heating_started_at,
            cycle_end=cycle_end,
            initial_temp=initial_temp,
            target_temp=target_temp,
            final_temp=final_temp,
            duration_minutes=actual_duration_minutes + error_minutes,
            final_slope=final_slope,
            initial_humidity=initial_humidity,
            final_humidity=final_humidity,
            initial_outdoor_temp=initial_outdoor_temp,
            initial_outdoor_humidity=initial_outdoor_humidity,
            initial_cloud_coverage=initial_cloud_coverage,
            final_outdoor_temp=final_outdoor_temp,
            final_outdoor_humidity=final_outdoor_humidity,
            final_cloud_coverage=final_cloud_coverage,
        )
    
    @pytest.mark.asyncio
    async def test_train_model_with_valid_cycles(self) -> None:
        """Test training model with valid heating cycles."""
        # GIVEN: Valid heating cycles
        cycles = [
            self._create_test_cycle(
                cycle_id=f"cycle_{i}",
                heating_started_at=datetime(2024, 1, i+1, 6, 0, 0),
            )
            for i in range(15)  # Need at least 10 cycles
        ]
        
        self.historical_reader.get_heating_cycles.return_value = cycles
        
        # Mock power history for cycle validation
        power_history = [
            (datetime(2024, 1, 1, 4, 0, 0), 50.0),
            (datetime(2024, 1, 1, 5, 0, 0), 50.0),
        ]
        self.historical_reader.get_radiator_power_history.return_value = power_history
        
        # Mock model storage
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            climate_entity_id="test_room",
            weather_entity_id="weather.test",
            humidity_entity_id="humidity.test",
            lookback_months=6,
            min_cycles=10,
        )
        
        # THEN: Model should be trained successfully
        assert result["status"] == "training_complete"
        assert result["cycles_extracted"] == 15
        assert result["cycles_valid"] == 15
        assert result["training_examples"] == 15
        assert "rmse" in result
        assert "mae" in result
        assert result["n_features"] > 0
        
        # Verify model was saved
        self.model_storage.save_model.assert_called_once()
        save_call_args = self.model_storage.save_model.call_args
        assert save_call_args[1]["climate_entity_id"] == "test_room"
        assert save_call_args[1]["model_data"] is not None
        assert "metadata" in save_call_args[1]
    
    @pytest.mark.asyncio
    async def test_train_model_insufficient_cycles(self) -> None:
        """Test training with insufficient cycles raises error."""
        # GIVEN: Too few cycles
        cycles = [
            self._create_test_cycle(cycle_id=f"cycle_{i}")
            for i in range(5)  # Less than min_cycles=10
        ]
        
        self.historical_reader.get_heating_cycles.return_value = cycles
        
        # Mock power history for cycle validation
        power_history = [
            (datetime(2024, 1, 1, 4, 0, 0), 50.0),
        ]
        self.historical_reader.get_radiator_power_history.return_value = power_history
        
        # WHEN/THEN: Should raise ValueError
        with pytest.raises(ValueError, match="Insufficient training data"):
            await self.service.train_model_for_room(
                climate_entity_id="test_room",
                weather_entity_id="weather.test",
                humidity_entity_id="humidity.test",
                min_cycles=10,
            )
   
    
    @pytest.mark.asyncio
    async def test_train_model_with_incomplete_history(self) -> None:
        """Test that training uses only cycle start data.
        
        Features are extracted only from data available at cycle start,
        so all valid cycles can be used regardless of historical data availability.
        """
        # GIVEN: Valid cycles but insufficient history for some
        cycles = [
            self._create_test_cycle(
                cycle_id=f"cycle_{i}",
                heating_started_at=datetime(2024, 1, i+1, 6, 0, 0),
            )
            for i in range(15)
        ]
        
        self.historical_reader.get_heating_cycles.return_value = cycles
        
        # Mock power history for cycle validation
        power_history = [
            (datetime(2024, 1, 1, 4, 0, 0), 50.0),
        ]
        self.historical_reader.get_radiator_power_history.return_value = power_history
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            climate_entity_id="test_room",
            weather_entity_id="weather.test",
            humidity_entity_id="humidity.test",
            min_cycles=10,
        )
        
        # THEN: Should successfully train with all cycles
        # All cycles have data at cycle start, so all can be used
        assert result["status"] == "training_complete"
        assert result["cycles_valid"] == 15
        assert result["training_examples"] == 15  # All cycles used
    
    @pytest.mark.asyncio
    async def test_train_model_creates_correct_features(self) -> None:
        """Test that feature engineering is called correctly."""
        # GIVEN: A single valid cycle
        cycle = self._create_test_cycle(
            cycle_id="test_cycle",
            heating_started_at=datetime(2024, 1, 15, 6, 0, 0),
            initial_temp=18.0,
            target_temp=21.0,
        )
        
        self.historical_reader.get_heating_cycles.return_value = [cycle] * 12
        
        # Mock power history for cycle validation
        power_history = [
            (datetime(2024, 1, 15, 5, 0, 0), 50.0),
            (datetime(2024, 1, 15, 6, 0, 0), 50.0),
        ]
        self.historical_reader.get_radiator_power_history.return_value = power_history
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            climate_entity_id="test_room",
            weather_entity_id="weather.test",
            humidity_entity_id="humidity.test", 
            min_cycles=10,
        )
        
        # THEN: Should successfully train
        assert result["status"] == "training_complete"
        assert result["training_examples"] == 12
