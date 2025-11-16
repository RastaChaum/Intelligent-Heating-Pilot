"""Tests for HASchedulerReader adapter."""
import unittest
from datetime import datetime
from unittest.mock import Mock, MagicMock
import sys
import os

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../../custom_components/intelligent_heating_pilot",
    ),
)

from infrastructure.adapters.scheduler_reader import HASchedulerReader
from domain.value_objects import ScheduleTimeslot


class TestHASchedulerReader(unittest.TestCase):
    """Tests for HASchedulerReader adapter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.scheduler_entities = ["switch.heating_schedule"]
        self.reader = HASchedulerReader(self.mock_hass, self.scheduler_entities)
    
    def test_init(self):
        """Test adapter initialization."""
        self.assertEqual(self.reader._scheduler_entity_ids, self.scheduler_entities)
        self.assertEqual(self.reader._hass, self.mock_hass)
    
    def test_get_next_timeslot_no_entities(self):
        """Test getting timeslot when no entities configured."""
        reader = HASchedulerReader(self.mock_hass, [])
        
        # Execute
        import asyncio
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert
        self.assertIsNone(result)
    
    def test_get_next_timeslot_entity_not_found(self):
        """Test getting timeslot when entity doesn't exist."""
        # Mock: entity not found
        self.mock_hass.states.get.return_value = None
        
        # Execute
        import asyncio
        result = asyncio.run(self.reader.get_next_timeslot())
        
        # Assert
        self.assertIsNone(result)
        self.mock_hass.states.get.assert_called_once_with("switch.heating_schedule")
    
    def test_get_next_timeslot_standard_format(self):
        """Test getting timeslot with standard scheduler format."""
        # Mock: scheduler state with standard format
        mock_state = Mock()
        mock_state.attributes = {
            "next_trigger": "2024-01-15T07:00:00+01:00",
            "next_slot": 0,
            "actions": [
                {
                    "service": "climate.set_temperature",
                    "data": {"temperature": 21.0}
                }
            ]
        }
        self.mock_hass.states.get.return_value = mock_state
        
        # Execute
        import asyncio
        result = asyncio.run(self.reader.get_next_timeslot())
        
        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, ScheduleTimeslot)
        self.assertEqual(result.target_temp, 21.0)
        self.assertIsNotNone(result.target_time)
        self.assertTrue(result.timeslot_id.startswith("switch.heating_schedule_"))
    
    def test_get_next_timeslot_multiple_entities(self):
        """Test getting earliest timeslot from multiple schedulers."""
        # Setup multiple schedulers
        reader = HASchedulerReader(
            self.mock_hass,
            ["switch.schedule_1", "switch.schedule_2"]
        )
        
        # Mock: two scheduler states
        mock_state_1 = Mock()
        mock_state_1.attributes = {
            "next_trigger": "2024-01-15T08:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
        }
        
        mock_state_2 = Mock()
        mock_state_2.attributes = {
            "next_trigger": "2024-01-15T07:00:00+01:00",  # Earlier time
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}]
        }
        
        def mock_get_state(entity_id):
            if entity_id == "switch.schedule_1":
                return mock_state_1
            elif entity_id == "switch.schedule_2":
                return mock_state_2
            return None
        
        self.mock_hass.states.get.side_effect = mock_get_state
        
        # Execute
        import asyncio
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert: should return the earlier timeslot
        self.assertIsNotNone(result)
        self.assertEqual(result.target_temp, 22.0)
        self.assertTrue(result.timeslot_id.startswith("switch.schedule_2_"))
    
    def test_extract_temp_from_action_direct(self):
        """Test extracting temperature from direct set_temperature action."""
        action = {
            "service": "climate.set_temperature",
            "data": {"temperature": 21.5}
        }
        
        result = self.reader._extract_temp_from_action(action)
        
        self.assertEqual(result, 21.5)
    
    def test_extract_temp_from_action_invalid(self):
        """Test extracting temperature from invalid action."""
        # Test with no temperature
        action = {
            "service": "climate.set_temperature",
            "data": {}
        }
        result = self.reader._extract_temp_from_action(action)
        self.assertIsNone(result)
        
        # Test with invalid service
        action = {
            "service": "light.turn_on",
            "data": {"brightness": 255}
        }
        result = self.reader._extract_temp_from_action(action)
        self.assertIsNone(result)
        
        # Test with non-dict action
        result = self.reader._extract_temp_from_action("invalid")
        self.assertIsNone(result)
    
    def test_parse_next_trigger_valid_iso(self):
        """Test parsing valid ISO datetime string."""
        trigger_str = "2024-01-15T07:30:00+01:00"
        
        result = self.reader._parse_next_trigger(trigger_str)
        
        self.assertIsNotNone(result)
        self.assertIsInstance(result, datetime)
        self.assertIsNotNone(result.tzinfo)  # Should have timezone
    
    def test_parse_next_trigger_none(self):
        """Test parsing None trigger."""
        result = self.reader._parse_next_trigger(None)
        self.assertIsNone(result)
    
    def test_parse_next_trigger_invalid(self):
        """Test parsing invalid trigger string."""
        result = self.reader._parse_next_trigger("not a datetime")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
