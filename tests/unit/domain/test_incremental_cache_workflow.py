"""Integration tests for incremental cycle cache functionality."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

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

from domain.value_objects import HeatingCycle, CycleCacheData
from domain.interfaces import ICycleCache


class MockCycleCache(ICycleCache):
    """Mock implementation of ICycleCache for testing."""
    
    def __init__(self):
        """Initialize mock cache."""
        self._cache: dict[str, CycleCacheData] = {}
        self._retention_days = 30
    
    async def get_cache_data(self, device_id: str) -> CycleCacheData | None:
        """Get cached cycle data for a device."""
        return self._cache.get(device_id)
    
    async def append_cycles(
        self,
        device_id: str,
        new_cycles: list[HeatingCycle],
        search_end_time: datetime,
    ) -> None:
        """Append new cycles to the cache."""
        existing = self._cache.get(device_id)
        
        if existing:
            existing_cycles = list(existing.cycles)
        else:
            existing_cycles = []
        
        # Deduplicate
        existing_keys = {
            (cycle.start_time, cycle.device_id)
            for cycle in existing_cycles
        }
        
        unique_new_cycles = [
            cycle for cycle in new_cycles
            if (cycle.start_time, cycle.device_id) not in existing_keys
        ]
        
        all_cycles = existing_cycles + unique_new_cycles
        all_cycles.sort(key=lambda c: c.start_time)
        
        self._cache[device_id] = CycleCacheData(
            device_id=device_id,
            cycles=tuple(all_cycles),
            last_search_time=search_end_time,
            retention_days=self._retention_days,
        )
    
    async def prune_old_cycles(
        self,
        device_id: str,
        reference_time: datetime,
    ) -> None:
        """Remove cycles older than retention period."""
        cache_data = self._cache.get(device_id)
        if not cache_data:
            return
        
        cutoff_time = reference_time - timedelta(days=cache_data.retention_days)
        retained_cycles = [
            cycle for cycle in cache_data.cycles
            if cycle.start_time >= cutoff_time
        ]
        
        if len(retained_cycles) < len(cache_data.cycles):
            self._cache[device_id] = CycleCacheData(
                device_id=device_id,
                cycles=tuple(retained_cycles),
                last_search_time=cache_data.last_search_time,
                retention_days=cache_data.retention_days,
            )
    
    async def clear_cache(self, device_id: str) -> None:
        """Clear all cached cycles for a device."""
        if device_id in self._cache:
            del self._cache[device_id]
    
    async def get_last_search_time(self, device_id: str) -> datetime | None:
        """Get the timestamp of the last cycle search."""
        cache_data = self._cache.get(device_id)
        return cache_data.last_search_time if cache_data else None


class TestIncrementalCycleCache(unittest.TestCase):
    """Test incremental cycle cache workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        self.device_id = "climate.test_vtherm"
        self.cache = MockCycleCache()
    
    def _create_cycle(
        self,
        start_time: datetime,
        duration_hours: float = 1.0,
    ) -> HeatingCycle:
        """Helper to create a heating cycle."""
        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = 20.0
        target_temp = 20.5
        
        return HeatingCycle(
            device_id=self.device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None
        )
    
    async def _run_async_test(self, coro):
        """Helper to run async tests."""
        import asyncio
        return await coro
    
    def test_incremental_workflow(self):
        """Test complete incremental cache workflow."""
        import asyncio
        
        async def run_test():
            # Initial extraction (no cache exists)
            initial_cycles = [
                self._create_cycle(self.base_time - timedelta(days=5)),
                self._create_cycle(self.base_time - timedelta(days=3)),
            ]
            
            await self.cache.append_cycles(
                self.device_id,
                initial_cycles,
                self.base_time - timedelta(days=2),
            )
            
            # Verify cache created
            cache_data = await self.cache.get_cache_data(self.device_id)
            self.assertIsNotNone(cache_data)
            self.assertEqual(cache_data.cycle_count, 2)
            
            # Incremental update (add new cycles)
            last_search = await self.cache.get_last_search_time(self.device_id)
            self.assertEqual(last_search, self.base_time - timedelta(days=2))
            
            new_cycles = [
                self._create_cycle(self.base_time - timedelta(days=1)),
                self._create_cycle(self.base_time),
            ]
            
            await self.cache.append_cycles(
                self.device_id,
                new_cycles,
                self.base_time + timedelta(hours=1),
            )
            
            # Verify incremental append
            cache_data = await self.cache.get_cache_data(self.device_id)
            self.assertEqual(cache_data.cycle_count, 4)
            
            # Verify no duplicate on re-append
            await self.cache.append_cycles(
                self.device_id,
                [self._create_cycle(self.base_time)],  # Duplicate
                self.base_time + timedelta(hours=2),
            )
            
            cache_data = await self.cache.get_cache_data(self.device_id)
            self.assertEqual(cache_data.cycle_count, 4)  # Still 4, not 5
            
            # Test retention filtering
            cycles_in_retention = cache_data.get_cycles_within_retention(
                self.base_time + timedelta(days=1)
            )
            self.assertEqual(len(cycles_in_retention), 4)  # All within 30 days
            
            # Test pruning
            await self.cache.prune_old_cycles(
                self.device_id,
                self.base_time + timedelta(days=26),  # 31 days from oldest
            )
            
            cache_data = await self.cache.get_cache_data(self.device_id)
            self.assertEqual(cache_data.cycle_count, 3)  # One pruned
        
        asyncio.run(run_test())
    
    def test_empty_period_handling(self):
        """Test that empty periods (no cycles) update last_search_time."""
        import asyncio
        
        async def run_test():
            # Initial data
            initial_cycles = [self._create_cycle(self.base_time)]
            await self.cache.append_cycles(
                self.device_id,
                initial_cycles,
                self.base_time + timedelta(hours=1),
            )
            
            # Search period with no cycles
            await self.cache.append_cycles(
                self.device_id,
                [],  # Empty list
                self.base_time + timedelta(days=1),
            )
            
            # last_search_time should still update
            last_search = await self.cache.get_last_search_time(self.device_id)
            self.assertEqual(last_search, self.base_time + timedelta(days=1))
            
            # Cycle count should remain unchanged
            cache_data = await self.cache.get_cache_data(self.device_id)
            self.assertEqual(cache_data.cycle_count, 1)
        
        asyncio.run(run_test())
    
    def test_cache_clear(self):
        """Test clearing cache."""
        import asyncio
        
        async def run_test():
            # Add data
            cycles = [self._create_cycle(self.base_time)]
            await self.cache.append_cycles(self.device_id, cycles, self.base_time)
            
            # Verify exists
            self.assertIsNotNone(await self.cache.get_cache_data(self.device_id))
            
            # Clear
            await self.cache.clear_cache(self.device_id)
            
            # Verify cleared
            self.assertIsNone(await self.cache.get_cache_data(self.device_id))
        
        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
