"""Tests for HASchedulerCommander adapter."""
import unittest
from datetime import datetime
from unittest.mock import Mock, AsyncMock
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

from infrastructure.adapters.scheduler_commander import (
    HASchedulerCommander,
    SCHEDULER_DOMAIN,
    SERVICE_RUN_ACTION,
)


class TestHASchedulerCommander(unittest.TestCase):
    """Tests for HASchedulerCommander adapter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.mock_hass.services.async_call = AsyncMock()
        self.scheduler_entity = "switch.heating_schedule"
        self.commander = HASchedulerCommander(self.mock_hass, self.scheduler_entity)
    
    def test_init(self):
        """Test adapter initialization."""
        self.assertEqual(self.commander._scheduler_entity_id, self.scheduler_entity)
        self.assertEqual(self.commander._hass, self.mock_hass)
    
    def test_run_action_success(self):
        """Test running scheduler action successfully."""
        import asyncio
        
        # Setup
        target_time = datetime(2024, 1, 15, 7, 30)
        
        # Execute
        asyncio.run(self.commander.run_action(target_time))
        
        # Assert
        self.mock_hass.services.async_call.assert_called_once_with(
            SCHEDULER_DOMAIN,
            SERVICE_RUN_ACTION,
            {
                "entity_id": self.scheduler_entity,
                "time": "07:30",
                "skip_conditions": False
            },
            blocking=True
        )
    
    def test_run_action_no_entity(self):
        """Test running action when no entity configured."""
        import asyncio
        
        # Setup: commander with no entity
        commander = HASchedulerCommander(self.mock_hass, "")
        target_time = datetime(2024, 1, 15, 7, 30)
        
        # Execute & Assert
        with self.assertRaises(ValueError) as context:
            asyncio.run(commander.run_action(target_time))
        
        self.assertIn("not configured", str(context.exception))
        self.mock_hass.services.async_call.assert_not_called()
    
    def test_run_action_service_fails(self):
        """Test handling service call failure."""
        import asyncio
        
        # Setup: mock service call to raise exception
        self.mock_hass.services.async_call = AsyncMock(
            side_effect=Exception("Service call failed")
        )
        target_time = datetime(2024, 1, 15, 7, 30)
        
        # Execute & Assert
        with self.assertRaises(Exception) as context:
            asyncio.run(self.commander.run_action(target_time))
        
        self.assertIn("Service call failed", str(context.exception))
    
    def test_cancel_action_success(self):
        """Test canceling action successfully."""
        import asyncio
        
        # Execute
        asyncio.run(self.commander.cancel_action())
        
        # Assert: should call service with current time
        self.mock_hass.services.async_call.assert_called_once()
        call_args = self.mock_hass.services.async_call.call_args
        
        self.assertEqual(call_args[0][0], SCHEDULER_DOMAIN)
        self.assertEqual(call_args[0][1], SERVICE_RUN_ACTION)
        
        # Check that time is in HH:MM format
        service_data = call_args[0][2]
        self.assertIn("time", service_data)
        self.assertRegex(service_data["time"], r"^\d{2}:\d{2}$")
    
    def test_cancel_action_no_entity(self):
        """Test canceling action when no entity configured."""
        import asyncio
        
        # Setup: commander with no entity
        commander = HASchedulerCommander(self.mock_hass, "")
        
        # Execute & Assert
        with self.assertRaises(ValueError) as context:
            asyncio.run(commander.cancel_action())
        
        self.assertIn("not configured", str(context.exception))
        self.mock_hass.services.async_call.assert_not_called()
    
    def test_time_formatting(self):
        """Test that times are formatted correctly."""
        import asyncio
        
        # Test different times
        test_cases = [
            (datetime(2024, 1, 15, 7, 30), "07:30"),
            (datetime(2024, 1, 15, 0, 0), "00:00"),
            (datetime(2024, 1, 15, 23, 59), "23:59"),
            (datetime(2024, 1, 15, 12, 5), "12:05"),
        ]
        
        for target_time, expected_str in test_cases:
            # Reset mock
            self.mock_hass.services.async_call.reset_mock()
            
            # Execute
            asyncio.run(self.commander.run_action(target_time))
            
            # Assert
            call_args = self.mock_hass.services.async_call.call_args
            service_data = call_args[0][2]
            self.assertEqual(service_data["time"], expected_str)


if __name__ == "__main__":
    unittest.main()
