"""Tests for CycleLabelingService."""
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

from domain.services.cycle_labeling_service import CycleLabelingService
from domain.value_objects import HeatingCycle


class TestCycleLabelingService(unittest.TestCase):
    """Tests for CycleLabelingService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = CycleLabelingService()

    def test_label_heating_cycle(self):
        """Test labeling a valid heating cycle."""
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
        
        duration = self.service.label_heating_cycle(cycle)
        self.assertEqual(duration, 60.0)

    def test_is_cycle_valid_for_training_valid_cycle(self):
        """Test that a valid cycle passes validation."""
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
        
        self.assertTrue(self.service.is_cycle_valid_for_training(cycle))

    def test_is_cycle_valid_rejects_too_short_duration(self):
        """Test that cycles with too short duration are rejected."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=3)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=3.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=18.5,
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
        
        self.assertFalse(self.service.is_cycle_valid_for_training(cycle))

    def test_is_cycle_valid_rejects_too_long_duration(self):
        """Test that cycles with too long duration are rejected."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=400)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=400.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=21.0,
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
        
        self.assertFalse(self.service.is_cycle_valid_for_training(cycle))

    def test_is_cycle_valid_rejects_insufficient_temp_increase(self):
        """Test that cycles with insufficient temperature increase are rejected."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=60)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=60.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=18.05,  # Only 0.05°C increase
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
        
        self.assertFalse(self.service.is_cycle_valid_for_training(cycle))

    def test_is_cycle_valid_custom_thresholds(self):
        """Test validation with custom threshold parameters."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(minutes=10)
        
        cycle = HeatingCycle(
            climate_entity_id="climate.bedroom",
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            duration_minutes=10.0,
            initial_temp=18.0,
            target_temp=21.0,
            final_temp=18.3,
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
        
        # Should pass with default thresholds (min_duration=5.0, min_temp_increase=0.1)
        self.assertTrue(self.service.is_cycle_valid_for_training(cycle))
        
        # Should be rejected with stricter thresholds
        self.assertFalse(
            self.service.is_cycle_valid_for_training(
                cycle,
                min_duration_minutes=15.0,
                min_temp_increase=0.5,
            )
        )


if __name__ == "__main__":
    unittest.main()
