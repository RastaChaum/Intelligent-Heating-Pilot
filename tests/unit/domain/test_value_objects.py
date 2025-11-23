"""Tests for domain value objects."""
import unittest
from datetime import datetime, timedelta

import sys
import os

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects import (
    EnvironmentState,
    ScheduleTimeslot,
    PredictionResult,
    HeatingDecision,
    HeatingAction,
    HeatingCycle,
)

# Import fixtures
sys.path.insert(0, os.path.dirname(__file__))
from fixtures import (
    get_test_datetime,
    TEST_CURRENT_TEMP,
    TEST_TARGET_TEMP,
    TEST_OUTDOOR_TEMP,
    TEST_HUMIDITY,
    TEST_LEARNED_SLOPE,
    TEST_TIMESLOT_ID,
)


class TestEnvironmentState(unittest.TestCase):
    """Tests for EnvironmentState value object."""

    def test_create_valid_environment_state(self):
        """Test creating a valid environment state."""
        now = get_test_datetime()
        state = EnvironmentState(
            current_temp=TEST_CURRENT_TEMP,
            outdoor_temp=TEST_OUTDOOR_TEMP,
            humidity=TEST_HUMIDITY,
            timestamp=now,
        )
        
        self.assertEqual(state.current_temp, TEST_CURRENT_TEMP)
        self.assertEqual(state.outdoor_temp, TEST_OUTDOOR_TEMP)
        self.assertEqual(state.humidity, TEST_HUMIDITY)
        self.assertEqual(state.timestamp, now)

    def test_environment_state_with_optional_fields(self):
        """Test environment state with optional fields."""
        now = datetime.now()
        state = EnvironmentState(
            current_temp=20.0,
            outdoor_temp=10.0,
            humidity=50.0,
            timestamp=now,
            outdoor_humidity=60.0,
            cloud_coverage=75.0,
        )
        
        self.assertEqual(state.outdoor_humidity, 60.0)
        self.assertEqual(state.cloud_coverage, 75.0)

    def test_environment_state_humidity_validation(self):
        """Test that humidity must be between 0 and 100."""
        now = datetime.now()
        
        with self.assertRaises(ValueError):
            EnvironmentState(
                current_temp=20.0,
                outdoor_temp=10.0,
                humidity=150.0,  # Invalid
                timestamp=now,
            )
        
        with self.assertRaises(ValueError):
            EnvironmentState(
                current_temp=20.0,
                outdoor_temp=10.0,
                humidity=-10.0,  # Invalid
                timestamp=now,
            )

    def test_environment_state_is_immutable(self):
        """Test that EnvironmentState is immutable."""
        now = datetime.now()
        state = EnvironmentState(
            current_temp=20.0,
            outdoor_temp=10.0,
            humidity=50.0,
            timestamp=now,
        )
        
        with self.assertRaises(AttributeError):
            state.current_temp = 25.0  # Should fail


class TestScheduleTimeslot(unittest.TestCase):
    """Tests for ScheduleTimeslot value object."""

    def test_create_valid_schedule_event(self):
        """Test creating a valid schedule event."""
        target_time = datetime.now()
        event = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_event_1",
        )
        
        self.assertEqual(event.target_time, target_time)
        self.assertEqual(event.target_temp, 21.0)
        self.assertEqual(event.timeslot_id, "test_event_1")

    def test_schedule_event_requires_id(self):
        """Test that timeslot_id cannot be empty."""
        target_time = datetime.now()
        
        with self.assertRaises(ValueError):
            ScheduleTimeslot(
                target_time=target_time,
                target_temp=21.0,
                timeslot_id="",  # Invalid
            )

    def test_schedule_event_is_immutable(self):
        """Test that ScheduleTimeslot is immutable."""
        target_time = datetime.now()
        event = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_event_1",
        )
        
        with self.assertRaises(AttributeError):
            event.target_temp = 22.0  # Should fail


class TestPredictionResult(unittest.TestCase):
    """Tests for PredictionResult value object."""

    def test_create_valid_prediction_result(self):
        """Test creating a valid prediction result."""
        start_time = datetime.now()
        result = PredictionResult(
            anticipated_start_time=start_time,
            estimated_duration_minutes=90.0,
            confidence_level=0.85,
            learned_heating_slope=2.0,
        )
        
        self.assertEqual(result.anticipated_start_time, start_time)
        self.assertEqual(result.estimated_duration_minutes, 90.0)
        self.assertEqual(result.confidence_level, 0.85)
        self.assertEqual(result.learned_heating_slope, 2.0)

    def test_prediction_result_validation(self):
        """Test prediction result validation."""
        start_time = datetime.now()
        
        # Negative duration
        with self.assertRaises(ValueError):
            PredictionResult(
                anticipated_start_time=start_time,
                estimated_duration_minutes=-10.0,  # Invalid
                confidence_level=0.85,
                learned_heating_slope=2.0,
            )
        
        # Invalid confidence (> 1.0)
        with self.assertRaises(ValueError):
            PredictionResult(
                anticipated_start_time=start_time,
                estimated_duration_minutes=90.0,
                confidence_level=1.5,  # Invalid
                learned_heating_slope=2.0,
            )
        
        # Invalid slope
        with self.assertRaises(ValueError):
            PredictionResult(
                anticipated_start_time=start_time,
                estimated_duration_minutes=90.0,
                confidence_level=0.85,
                learned_heating_slope=0.0,  # Invalid
            )


class TestHeatingDecision(unittest.TestCase):
    """Tests for HeatingDecision value object."""

    def test_create_start_heating_decision(self):
        """Test creating a START_HEATING decision."""
        decision = HeatingDecision(
            action=HeatingAction.START_HEATING,
            target_temp=21.0,
            reason="Time to start heating",
        )
        
        self.assertEqual(decision.action, HeatingAction.START_HEATING)
        self.assertEqual(decision.target_temp, 21.0)
        self.assertEqual(decision.reason, "Time to start heating")

    def test_start_heating_requires_target_temp(self):
        """Test that START_HEATING requires a target temperature."""
        with self.assertRaises(ValueError):
            HeatingDecision(
                action=HeatingAction.START_HEATING,
                target_temp=None,  # Invalid for START_HEATING
                reason="Time to start heating",
            )

    def test_create_no_action_decision(self):
        """Test creating a NO_ACTION decision."""
        decision = HeatingDecision(
            action=HeatingAction.NO_ACTION,
            reason="Already at target temperature",
        )
        
        self.assertEqual(decision.action, HeatingAction.NO_ACTION)
        self.assertIsNone(decision.target_temp)
        self.assertEqual(decision.reason, "Already at target temperature")


class TestHeatingCycle(unittest.TestCase):
    """Tests for HeatingCycle value object."""

    def test_create_valid_heating_cycle(self):
        """Test creating a valid heating cycle."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=60)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=60.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=20.5,
            initial_slope=0.5,
            final_slope=0.2,
            initial_humidity=50.0,
            final_humidity=48.0,
            initial_outdoor_temp=5.0,
            initial_outdoor_humidity=80.0,
            initial_cloud_coverage=50.0,
            final_outdoor_temp=6.0,
            final_outdoor_humidity=78.0,
            final_cloud_coverage=45.0,
        )
        
        self.assertEqual(cycle.climate_entity_id, "climate.bedroom")
        self.assertEqual(cycle.duration_minutes, 60.0)
        self.assertEqual(cycle.initial_temp, 18.0)
        self.assertEqual(cycle.target_temp, 21.0)
        self.assertEqual(cycle.final_temp, 20.5)
        self.assertIsNotNone(cycle.cycle_id)  # UUID should be generated

    def test_heating_cycle_with_minimal_fields(self):
        """Test heating cycle with only required fields."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=30)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=30.0,
            initial_temp=18.5,
            target_temp=21.0,
            final_temp=19.8,
            initial_slope=None,
            final_slope=None,
            initial_humidity=None,
            final_humidity=None,
            initial_outdoor_temp=None,
            initial_outdoor_humidity=None,
            initial_cloud_coverage=None,
            final_outdoor_temp=None,
            final_outdoor_humidity=None,
            final_cloud_coverage=None,
        )
        
        self.assertEqual(cycle.duration_minutes, 30.0)
        self.assertIsNone(cycle.initial_slope)
        self.assertIsNone(cycle.initial_humidity)

    def test_heating_cycle_negative_duration(self):
        """Test that negative duration is rejected."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=60)
        
        with self.assertRaises(ValueError):
            HeatingCycle(
                climate_entity_id="climate.bedroom",
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                duration_minutes=-10.0,  # Invalid
                initial_temp=18.0,
                target_temp=21.0,
                final_temp=20.5,
                initial_slope=None,
                final_slope=None,
                initial_humidity=None,
                final_humidity=None,
                initial_outdoor_temp=None,
                initial_outdoor_humidity=None,
                initial_cloud_coverage=None,
                final_outdoor_temp=None,
                final_outdoor_humidity=None,
                final_cloud_coverage=None,
            )

    def test_heating_cycle_initial_temp_above_target(self):
        """Test that initial_temp above target_temp is rejected."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=60)
        
        with self.assertRaises(ValueError):
            HeatingCycle(
                climate_entity_id="climate.bedroom",
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                duration_minutes=60.0,
                initial_temp=22.0,  # Above target
                target_temp=21.0,
                final_temp=21.5,
                initial_slope=None,
                final_slope=None,
                initial_humidity=None,
                final_humidity=None,
                initial_outdoor_temp=None,
                initial_outdoor_humidity=None,
                initial_cloud_coverage=None,
                final_outdoor_temp=None,
                final_outdoor_humidity=None,
                final_cloud_coverage=None,
            )

    def test_heating_cycle_is_immutable(self):
        """Test that HeatingCycle is immutable."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=60)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=60.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=20.5,
            initial_slope=None,
            final_slope=None,
            initial_humidity=None,
            final_humidity=None,
            initial_outdoor_temp=None,
            initial_outdoor_humidity=None,
            initial_cloud_coverage=None,
            final_outdoor_temp=None,
            final_outdoor_humidity=None,
            final_cloud_coverage=None,
        )
        
        with self.assertRaises(AttributeError):
            cycle.duration_minutes = 90.0  # Should fail


if __name__ == "__main__":
    unittest.main()
