"""Tests for HASchedulerReader adapter."""
import asyncio
import unittest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduleTimeslot,
)


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
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert
        self.assertIsNone(result)
    
    def test_get_next_timeslot_entity_not_found(self):
        """Test getting timeslot when entity doesn't exist."""
        # Mock: entity not found
        self.mock_hass.states.get.return_value = None
        
        # Execute
        result = asyncio.run(self.reader.get_next_timeslot())
        
        # Assert
        self.assertIsNone(result)
        self.mock_hass.states.get.assert_called_once_with("switch.heating_schedule")
    
    def test_get_next_timeslot_standard_format(self):
        """Test getting timeslot with standard scheduler format."""
        # Mock: scheduler state with standard format
        mock_state = Mock()
        mock_state.state = "on"  # Scheduler is enabled
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
        result = asyncio.run(self.reader.get_next_timeslot())
        
        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, ScheduleTimeslot)
        self.assertEqual(result.target_temp, 21.0)
        self.assertIsNotNone(result.target_time)
        self.assertTrue(result.timeslot_id.startswith("switch.heating_schedule_"))
    
    def test_get_next_timeslot_scheduler_disabled(self):
        """Test that disabled schedulers are skipped."""
        # Mock: scheduler state with "off" state
        mock_state = Mock()
        mock_state.state = "off"  # Scheduler is disabled
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
        result = asyncio.run(self.reader.get_next_timeslot())
        
        # Assert: should return None since scheduler is disabled
        self.assertIsNone(result)
    
    def test_get_next_timeslot_multiple_entities(self):
        """Test getting earliest timeslot from multiple schedulers."""
        # Setup multiple schedulers
        reader = HASchedulerReader(
            self.mock_hass,
            ["switch.schedule_1", "switch.schedule_2"]
        )
        
        # Mock: two scheduler states
        mock_state_1 = Mock()
        mock_state_1.state = "on"  # Enabled
        mock_state_1.attributes = {
            "next_trigger": "2024-01-15T08:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
        }
        
        mock_state_2 = Mock()
        mock_state_2.state = "on"  # Enabled
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
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert: should return the earlier timeslot
        self.assertIsNotNone(result)
        self.assertEqual(result.target_temp, 22.0)
        self.assertTrue(result.timeslot_id.startswith("switch.schedule_2_"))
    
    def test_get_next_timeslot_multiple_entities_one_disabled(self):
        """Test that only enabled schedulers are considered when multiple exist."""
        # Setup multiple schedulers
        reader = HASchedulerReader(
            self.mock_hass,
            ["switch.schedule_1", "switch.schedule_2"]
        )
        
        # Mock: one enabled, one disabled
        mock_state_1 = Mock()
        mock_state_1.state = "off"  # Disabled
        mock_state_1.attributes = {
            "next_trigger": "2024-01-15T06:00:00+01:00",  # Earlier time but disabled
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
        }
        
        mock_state_2 = Mock()
        mock_state_2.state = "on"  # Enabled
        mock_state_2.attributes = {
            "next_trigger": "2024-01-15T08:00:00+01:00",  # Later time but enabled
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
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert: should return the enabled scheduler's timeslot
        self.assertIsNotNone(result)
        self.assertEqual(result.target_temp, 22.0)
        self.assertTrue(result.timeslot_id.startswith("switch.schedule_2_"))
    
    def test_get_next_timeslot_all_disabled(self):
        """Test that no timeslot is returned when all schedulers are disabled."""
        # Setup multiple schedulers
        reader = HASchedulerReader(
            self.mock_hass,
            ["switch.schedule_1", "switch.schedule_2"]
        )
        
        # Mock: both disabled
        mock_state_1 = Mock()
        mock_state_1.state = "off"  # Disabled
        mock_state_1.attributes = {
            "next_trigger": "2024-01-15T07:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
        }
        
        mock_state_2 = Mock()
        mock_state_2.state = "off"  # Disabled
        mock_state_2.attributes = {
            "next_trigger": "2024-01-15T08:00:00+01:00",
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
        result = asyncio.run(reader.get_next_timeslot())
        
        # Assert: should return None since all schedulers are disabled
        self.assertIsNone(result)
    
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
    
    def test_resolve_preset_temperature_v8_format(self):
        """Test resolving preset temperature from VTherm v8.0.0+ format."""
        # Setup VTherm entity with v8.0.0+ preset_temperatures structure
        vtherm_state = Mock()
        vtherm_state.entity_id = "climate.test_vtherm"
        vtherm_state.attributes = {
            "preset_mode": "none",
            "preset_temperatures": {
                "eco_temp": 18.0,
                "boost_temp": 22.0,
                "comfort_temp": 20.0,
                "frost_temp": 10.0,
            }
        }
        
        reader = HASchedulerReader(
            self.mock_hass, 
            ["switch.schedule"], 
            vtherm_entity_id="climate.test_vtherm"
        )
        
        # Mock VTherm state
        self.mock_hass.states.get.return_value = vtherm_state
        
        # Test resolving eco preset
        result = reader._resolve_preset_temperature("eco")
        self.assertEqual(result, 18.0)
        
        # Test resolving boost preset
        result = reader._resolve_preset_temperature("boost")
        self.assertEqual(result, 22.0)
        
        # Test resolving comfort preset
        result = reader._resolve_preset_temperature("comfort")
        self.assertEqual(result, 20.0)
    
    def test_resolve_preset_temperature_ignores_zero_values(self):
        """Test that preset resolution ignores 0 values (uninitialized)."""
        # Setup VTherm with uninitialized presets
        vtherm_state = Mock()
        vtherm_state.entity_id = "climate.test_vtherm"
        vtherm_state.attributes = {
            "preset_mode": "none",
            "preset_temperatures": {
                "eco_temp": 0,  # Uninitialized
                "boost_temp": 0,  # Uninitialized
            }
        }
        
        reader = HASchedulerReader(
            self.mock_hass, 
            ["switch.schedule"], 
            vtherm_entity_id="climate.test_vtherm"
        )
        
        self.mock_hass.states.get.return_value = vtherm_state
        
        # Should return None for 0 values
        result = reader._resolve_preset_temperature("eco")
        self.assertIsNone(result)
    
    def test_is_scheduler_enabled_on(self):
        """Test that is_scheduler_enabled returns True for enabled schedulers."""
        mock_state = Mock()
        mock_state.state = "on"
        self.mock_hass.states.get.return_value = mock_state
        
        result = asyncio.run(self.reader.is_scheduler_enabled("switch.heating_schedule"))
        
        self.assertTrue(result)
        self.mock_hass.states.get.assert_called_once_with("switch.heating_schedule")
    
    def test_is_scheduler_enabled_off(self):
        """Test that is_scheduler_enabled returns False for disabled schedulers."""
        mock_state = Mock()
        mock_state.state = "off"
        self.mock_hass.states.get.return_value = mock_state
        
        result = asyncio.run(self.reader.is_scheduler_enabled("switch.heating_schedule"))
        
        self.assertFalse(result)
        self.mock_hass.states.get.assert_called_once_with("switch.heating_schedule")
    
    def test_is_scheduler_enabled_entity_not_found(self):
        """Test that is_scheduler_enabled returns False when entity not found."""
        self.mock_hass.states.get.return_value = None
        
        result = asyncio.run(self.reader.is_scheduler_enabled("switch.heating_schedule"))
        
        self.assertFalse(result)
        self.mock_hass.states.get.assert_called_once_with("switch.heating_schedule")


if __name__ == "__main__":
    unittest.main()
