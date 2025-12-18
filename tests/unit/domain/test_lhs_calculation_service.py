"""Tests for LHSCalculationService."""
import unittest
from datetime import datetime, timezone, timedelta

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

from domain.services import LHSCalculationService
from domain.value_objects import HeatingCycle


class TestLHSCalculationService(unittest.TestCase):
    """Tests for LHS calculation service."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = LHSCalculationService()
    
    def _create_cycle(
        self,
        start_time: datetime,
        duration_hours: float,
        temp_increase: float,
        device_id: str = "test_device"
    ) -> HeatingCycle:
        """Helper to create a heating cycle with specific slope."""
        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = start_temp + temp_increase
        target_temp = end_temp + 0.5  # Slightly above end temp
        
        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None
        )
    
    def test_calculate_global_lhs_empty_list(self):
        """Test calculating global LHS with empty list."""
        result = self.service.calculate_global_lhs([])
        
        # Should return default
        self.assertEqual(result, 2.0)
    
    def test_calculate_global_lhs_single_cycle(self):
        """Test calculating global LHS with a single cycle."""
        # Create a cycle with 2°C increase in 1 hour = 2°C/h slope
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        cycle = self._create_cycle(
            start_time=base_time,
            duration_hours=1.0,
            temp_increase=2.0
        )
        
        result = self.service.calculate_global_lhs([cycle])
        
        # Should return the cycle's slope
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_global_lhs_multiple_cycles(self):
        """Test calculating global LHS with multiple cycles."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        # Create cycles with different slopes: 2.0, 2.2, 2.4 °C/h
        cycles = [
            self._create_cycle(base_time, duration_hours=1.0, temp_increase=2.0),
            self._create_cycle(base_time + timedelta(hours=2), duration_hours=1.0, temp_increase=2.2),
            self._create_cycle(base_time + timedelta(hours=4), duration_hours=1.0, temp_increase=2.4),
        ]
        
        result = self.service.calculate_global_lhs(cycles)
        
        # Average should be (2.0 + 2.2 + 2.4) / 3 = 2.2
        self.assertAlmostEqual(result, 2.2, places=2)
    
    def test_calculate_global_lhs_with_varying_durations(self):
        """Test that global LHS handles cycles of different durations correctly."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        # Different durations but similar heating rates
        cycles = [
            self._create_cycle(base_time, duration_hours=0.5, temp_increase=1.0),  # 2.0°C/h
            self._create_cycle(base_time + timedelta(hours=1), duration_hours=2.0, temp_increase=4.0),  # 2.0°C/h
            self._create_cycle(base_time + timedelta(hours=4), duration_hours=1.0, temp_increase=2.0),  # 2.0°C/h
        ]
        
        result = self.service.calculate_global_lhs(cycles)
        
        # All have 2.0°C/h slope, average should be 2.0
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_contextual_lhs_empty_list(self):
        """Test calculating contextual LHS with empty list."""
        result = self.service.calculate_contextual_lhs([], target_hour=15)
        
        # Should return default
        self.assertEqual(result, 2.0)
    
    def test_calculate_contextual_lhs_invalid_hour(self):
        """Test calculating contextual LHS with invalid hour."""
        with self.assertRaises(ValueError):
            self.service.calculate_contextual_lhs([], target_hour=25)
        
        with self.assertRaises(ValueError):
            self.service.calculate_contextual_lhs([], target_hour=-1)
    
    def test_calculate_contextual_lhs_active_cycle(self):
        """Test contextual LHS includes cycles active at target hour."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        # Cycle from 14:00 to 16:00 (active at 15:00)
        cycle = self._create_cycle(
            start_time=base_time,
            duration_hours=2.0,
            temp_increase=4.0  # 2.0°C/h
        )
        
        result = self.service.calculate_contextual_lhs([cycle], target_hour=15)
        
        # Should include this cycle
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_contextual_lhs_excludes_inactive_cycle(self):
        """Test contextual LHS excludes cycles not active at target hour."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        # Cycle from 14:00 to 15:00 (NOT active at 16:00)
        cycle1 = self._create_cycle(
            start_time=base_time,
            duration_hours=1.0,
            temp_increase=1.0
        )

        # Cycle from 16:30 to 17:30 (NOT active at 16:00)
        cycle2 = self._create_cycle(
            start_time=base_time,
            duration_hours=1.0,
            temp_increase=2.0
        )        
        
        result = self.service.calculate_contextual_lhs([cycle1, cycle2], target_hour=16)
        
        # Should not include this cycle, return default
        self.assertEqual(result, 1.5)
    
    def test_calculate_contextual_lhs_filters_correctly(self):
        """Test contextual LHS filters cycles by activity at target hour."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        cycles = [
            # Cycle 1: 12:00-13:00 (NOT active at 15:00)
            self._create_cycle(base_time - timedelta(hours=2), duration_hours=1.0, temp_increase=1.0),  # 1.0°C/h
            
            # Cycle 2: 14:00-16:00 (ACTIVE at 15:00)
            self._create_cycle(base_time, duration_hours=2.0, temp_increase=4.0),  # 2.0°C/h
            
            # Cycle 3: 15:30-17:00 (ACTIVE at 15:00 - starts before 16:00)
            self._create_cycle(base_time + timedelta(hours=1.5), duration_hours=1.5, temp_increase=3.0),  # 2.0°C/h
            
            # Cycle 4: 17:00-18:00 (NOT active at 15:00)
            self._create_cycle(base_time + timedelta(hours=3), duration_hours=1.0, temp_increase=3.0),  # 3.0°C/h
        ]
        
        result = self.service.calculate_contextual_lhs(cycles, target_hour=15)
        
        # Should only average cycles 2 and 3 (both 2.0°C/h)
        # Average = (2.0 + 2.0) / 2 = 2.0
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_contextual_lhs_exact_hour_boundary(self):
        """Test contextual LHS at exact cycle boundaries."""
        base_time = datetime(2025, 12, 18, 15, 0, 0, tzinfo=timezone.utc)
        
        # Cycle starts exactly at target hour (15:00-16:00)
        cycle_at_hour = self._create_cycle(base_time, duration_hours=1.0, temp_increase=2.0)
        
        # Cycle ends exactly at target hour (14:00-15:00)
        cycle_before_hour = self._create_cycle(
            base_time - timedelta(hours=1),
            duration_hours=1.0,
            temp_increase=3.0
        )
        
        cycles = [cycle_at_hour, cycle_before_hour]
        result = self.service.calculate_contextual_lhs(cycles, target_hour=15)
        
        # Cycle ending at 15:00 is NOT active at 15:00 (exclusive end)
        # Only cycle starting at 15:00 should be included
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_contextual_lhs_crosses_midnight(self):
        """Test contextual LHS with cycles crossing midnight."""
        # Cycle from 23:00 to 01:00 (crosses midnight)
        night_cycle = self._create_cycle(
            start_time=datetime(2025, 12, 18, 23, 0, 0, tzinfo=timezone.utc),
            duration_hours=2.0,
            temp_increase=4.0  # 2.0°C/h
        )
        
        # Should be active at 00:00 (midnight)
        result = self.service.calculate_contextual_lhs([night_cycle], target_hour=0)
        self.assertAlmostEqual(result, 2.0, places=2)
        
        # Should also be active at 23:00
        result = self.service.calculate_contextual_lhs([night_cycle], target_hour=23)
        self.assertAlmostEqual(result, 2.0, places=2)
    
    def test_calculate_contextual_lhs_multiple_active_different_slopes(self):
        """Test contextual LHS averages multiple cycles with different slopes."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        
        cycles = [
            # All active at 15:00 but with different slopes
            self._create_cycle(base_time, duration_hours=2.0, temp_increase=2.0),     # 1.0°C/h
            self._create_cycle(base_time, duration_hours=2.0, temp_increase=4.0),     # 2.0°C/h
            self._create_cycle(base_time, duration_hours=2.0, temp_increase=6.0),     # 3.0°C/h
        ]
        
        result = self.service.calculate_contextual_lhs(cycles, target_hour=15)
        
        # Average = (1.0 + 2.0 + 3.0) / 3 = 2.0
        self.assertAlmostEqual(result, 2.0, places=2)


if __name__ == "__main__":
    unittest.main()
