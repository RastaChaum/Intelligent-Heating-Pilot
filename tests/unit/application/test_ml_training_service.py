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
        
        # Create service
        self.service = MLTrainingApplicationService(
            historical_reader=self.historical_reader,
            model_storage=self.model_storage,
        )
    
    def _create_test_cycle(
        self,
        cycle_id: str,
        room_id: str = "test_room",
        heating_started_at: datetime | None = None,
        target_reached_at: datetime | None = None,
        initial_temp: float = 18.0,
        target_temp: float = 21.0,
        final_temp: float = 21.0,
        actual_duration_minutes: float = 60.0,
        optimal_duration_minutes: float = 55.0,
        error_minutes: float = 5.0,
    ) -> HeatingCycle:
        """Create a test heating cycle."""
        if heating_started_at is None:
            heating_started_at = datetime(2024, 1, 15, 6, 0, 0)
        if target_reached_at is None:
            target_reached_at = heating_started_at + timedelta(
                minutes=actual_duration_minutes + error_minutes
            )
        
        target_time = heating_started_at + timedelta(minutes=actual_duration_minutes)
        
        return HeatingCycle(
            cycle_id=cycle_id,
            room_id=room_id,
            heating_started_at=heating_started_at,
            target_time=target_time,
            target_reached_at=target_reached_at,
            initial_temp=initial_temp,
            target_temp=target_temp,
            final_temp=final_temp,
            outdoor_temp=10.0,
            humidity=50.0,
            actual_duration_minutes=actual_duration_minutes,
            optimal_duration_minutes=optimal_duration_minutes,
            error_minutes=error_minutes,
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
        
        # Mock temperature and power history for each cycle
        temp_history = [
            (datetime(2024, 1, 1, 4, 0, 0), 17.0),
            (datetime(2024, 1, 1, 4, 30, 0), 17.5),
            (datetime(2024, 1, 1, 5, 0, 0), 18.0),
            (datetime(2024, 1, 1, 5, 30, 0), 18.0),
        ]
        power_history = [
            (datetime(2024, 1, 1, 4, 0, 0), False),
            (datetime(2024, 1, 1, 5, 0, 0), False),
        ]
        
        self.historical_reader.get_temperature_history.return_value = temp_history
        self.historical_reader.get_power_state_history.return_value = power_history
        
        # Mock model storage
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            room_id="test_room",
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
        assert save_call_args[1]["room_id"] == "test_room"
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
        
        # WHEN/THEN: Should raise ValueError
        with pytest.raises(ValueError, match="Insufficient training data"):
            await self.service.train_model_for_room(
                room_id="test_room",
                min_cycles=10,
            )
    
    @pytest.mark.asyncio
    async def test_train_model_filters_invalid_cycles(self) -> None:
        """Test that invalid cycles are filtered out."""
        # GIVEN: Mix of valid and invalid cycles
        valid_cycles = [
            self._create_test_cycle(
                cycle_id=f"valid_{i}",
                heating_started_at=datetime(2024, 1, i+1, 6, 0, 0),
            )
            for i in range(12)
        ]
        
        # Invalid cycle: target never reached
        # Create manually to bypass validation that would prevent None target_reached_at
        invalid_cycle = HeatingCycle(
            cycle_id="invalid_1",
            room_id="test_room",
            heating_started_at=datetime(2024, 1, 13, 6, 0, 0),
            target_time=datetime(2024, 1, 13, 7, 0, 0),
            target_reached_at=None,  # Invalid: target never reached
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=19.0,  # Didn't reach target
            outdoor_temp=10.0,
            humidity=50.0,
            actual_duration_minutes=60.0,
            optimal_duration_minutes=0.0,  # Set to 0 since invalid
            error_minutes=0.0,
        )
        
        cycles = valid_cycles + [invalid_cycle]
        self.historical_reader.get_heating_cycles.return_value = cycles
        
        # Mock history
        temp_history = [
            (datetime(2024, 1, 1, 4, 0, 0), 17.0),
            (datetime(2024, 1, 1, 5, 0, 0), 18.0),
        ]
        power_history = [
            (datetime(2024, 1, 1, 4, 0, 0), False),
        ]
        
        self.historical_reader.get_temperature_history.return_value = temp_history
        self.historical_reader.get_power_state_history.return_value = power_history
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            room_id="test_room",
            min_cycles=10,
        )
        
        # THEN: Invalid cycle should be filtered
        assert result["cycles_extracted"] == 13
        assert result["cycles_valid"] == 12  # Invalid one filtered
        assert result["training_examples"] == 12
    
    @pytest.mark.asyncio
    async def test_train_model_with_incomplete_history(self) -> None:
        """Test that training handles cycles with incomplete history gracefully.
        
        When historical data is missing, lagged features are set to None,
        which are then converted to 0.0 for ML training. This allows
        training to proceed even with incomplete data.
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
        
        # Mock history - empty for first few calls (simulating missing data)
        call_count = 0
        
        def get_temp_history_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # Return insufficient history for first 3 cycles
                # These will have None lagged features, converted to 0.0
                return []
            return [
                (datetime(2024, 1, 1, 4, 0, 0), 17.0),
                (datetime(2024, 1, 1, 5, 0, 0), 18.0),
            ]
        
        self.historical_reader.get_temperature_history.side_effect = (
            get_temp_history_side_effect
        )
        self.historical_reader.get_power_state_history.return_value = [
            (datetime(2024, 1, 1, 4, 0, 0), False),
        ]
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            room_id="test_room",
            min_cycles=10,
        )
        
        # THEN: Should successfully train with all cycles
        # Missing lagged features are converted to 0.0, so all cycles are used
        assert result["status"] == "training_complete"
        assert result["cycles_valid"] == 15
        assert result["training_examples"] == 15  # All cycles used, None -> 0.0
    
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
        
        # Mock detailed history
        cycle_start = datetime(2024, 1, 15, 6, 0, 0)
        temp_history = [
            (cycle_start - timedelta(minutes=90), 17.0),
            (cycle_start - timedelta(minutes=60), 17.5),
            (cycle_start - timedelta(minutes=30), 18.0),
            (cycle_start - timedelta(minutes=15), 18.0),
        ]
        power_history = [
            (cycle_start - timedelta(minutes=90), False),
            (cycle_start - timedelta(minutes=30), False),
        ]
        
        self.historical_reader.get_temperature_history.return_value = temp_history
        self.historical_reader.get_power_state_history.return_value = power_history
        self.model_storage.save_model.return_value = None
        
        # WHEN: Training model
        result = await self.service.train_model_for_room(
            room_id="test_room",
            min_cycles=10,
        )
        
        # THEN: Should successfully train
        assert result["status"] == "training_complete"
        assert result["training_examples"] == 12
        
        # Verify history was fetched for each cycle
        assert self.historical_reader.get_temperature_history.call_count == 12
        assert self.historical_reader.get_power_state_history.call_count == 12
        
        # Verify history fetch used correct time range (120 min before start)
        first_call = self.historical_reader.get_temperature_history.call_args_list[0]
        assert first_call[1]["start_time"] == cycle_start - timedelta(minutes=120)
        assert first_call[1]["end_time"] == cycle_start
