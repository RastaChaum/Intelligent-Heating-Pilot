# Contextual Learned Heating Slope (LHS) Architecture Design

**Status:** Design Phase
**Target Implementation:** Phase 2
**Last Updated:** 2026-02-09

---

## Table of Contents

1. [Overview](#overview)
2. [Behavior Specification](#behavior-specification)
3. [Data Structures](#data-structures)
4. [Cache Management Strategy](#cache-management-strategy)
5. [Data Flow](#data-flow)
6. [Architecture Components](#architecture-components)
7. [File Structure & Skeleton Code](#file-structure--skeleton-code)
8. [Integration Points](#integration-points)
9. [Test Coverage Plan](#test-coverage-plan)
10. [Open Questions & Trade-offs](#open-questions--trade-offs)

---

## Overview

### Current Problem

The contextual LHS system needs fundamental revisions:
- `get_contextual_learned_heating_slope(hour)` currently returns the **global LHS** (incorrect)
- It should return: **Average LHS of all cycles whose start_hour matches the Next Schedule Time hour** + **cycle_count**
- Each cycle MUST have its own LHS value stored (not calculated later)
- LHS must be recalculated **on every cycle addition** (not just 24h refresh)
- If no Next Schedule Time (no scheduler configured), return `None` → sensor shows "unknown"

### Solution Vision

```
Extract Heating Cycles
  ↓
[For Each Cycle (with LHS calculated)]
  ├─ Cycle object includes: start_time, end_time, lhs_value
  ├─ Extract start_hour from cycle.start_time
  ├─ Recalculate GLOBAL LHS (GlobalLHSCalculatorService)
  │  └─ Average of ALL cycles with count
  └─ Recalculate CONTEXTUAL LHS (ContextualLHSCalculatorService)
     └─ Group by start_hour
     └─ For each hour: {lhs: avg, cycle_count: int}
  ↓
On Cycle Addition (NOT just 24h):
  ├─ Redémarrage → Extract all → Recalc both
  ├─ Retention change → Re-extract → Recalc both
  └─ New cycles detected → Recalc both
  ↓
On Sensor Read:
  ├─ Get Next Schedule Time from coordinator
  ├─ Extract hour from Next Schedule Time
  ├─ Lookup cache[hour] → {lhs, cycle_count}
  └─ Return {lhs: 14.75, count: 3} OR None
```

### Key Changes from Initial Design

1. **Cycle Storage**: Each cycle now HAS its own LHS (not calculated separately)
2. **Cache Structure**: Per-hour cache includes `{lhs: float, cycle_count: int, updated_at: datetime}`
3. **Recalculation Trigger**: On EVERY cycle addition event (redémarrage, retention change, new cycles)
4. **Service Architecture**: TWO specialized calculators
   - `GlobalLHSCalculatorService` → Single value: avg(ALL cycles)
   - `ContextualLHSCalculatorService` → 24 values: one per hour with metadata

### Key Insight: Hour-Based Grouping

A cycle is "part of hour X" if it **started at or during hour X** (ignoring date):
- Cycle starts `2025-02-08 06:15` → belongs to hour 6
- Cycle ends at `2025-02-08 07:00` → still belongs to hour 6 (started at 6)
- This is **different** from "active during hour X" (which would require checking if cycle spans that hour)


---

## Behavior Specification

### Scenario A: Scheduler Active + Cycles Exist for Hour

**Setup:**
```
Next Schedule Time:  2025-02-09 06:00 (hour=6)
Extracted cycles:
  - Cycle(start_time=2025-02-08 06:15, end_time=2025-02-08 07:00, lhs=15.0)
  - Cycle(start_time=2025-02-07 06:30, end_time=2025-02-07 07:15, lhs=14.5)
```

**Expected:**
```
contextual_lhs = 14.75°C/h (average of [15.0, 14.5])
```

**User sees:**
- Sensor value: `14.75`
- Attributes: `{"description": "Average LHS for cycles starting at 06:00", "schedule_hour": "06"}`

---

### Scenario B: Scheduler Active + NO Cycles for Hour

**Setup:**
```
Next Schedule Time:  2025-02-09 12:00 (hour=12)
Extracted cycles:
  - Cycle(start_time=2025-02-08 06:15, lhs=15.0)
  - Cycle(start_time=2025-02-08 08:00, lhs=14.5)
  (no cycles starting at hour 12)
```

**Expected:**
```
contextual_lhs = None (no data for this hour)
```

**User sees:**
- Sensor value: `"unknown"`
- Attributes: `{"description": "No cycles available for scheduled hour", "schedule_hour": "12"}`

---

### Scenario C: No Scheduler Configured

**Setup:**
```
scheduler_entities = []
Next Schedule Time = None
Cycles exist but unused
```

**Expected:**
```
contextual_lhs = None (no schedule to reference)
```

**User sees:**
- Sensor value: `"unknown"`
- Attributes: `{"description": "No scheduler configured", "schedule_hour": null}`

---

### Scenario D: Next Schedule Time Available but Calculation Fails

**Setup:**
```
Next Schedule Time exists
Coordinator.get_next_schedule_time() throws exception
```

**Expected:**
```
contextual_lhs = None (graceful fallback)
Logs: WARNING "Failed to calculate contextual LHS due to exception"
```

---

## Data Structures

### Value Objects

#### 1. **LHSCacheEntry** (Existing - Enhanced)

```python
@dataclass(frozen=True)
class LHSCacheEntry:
    """Represents a cached LHS value and its metadata.

    Attributes:
        value: The LHS value in °C/hour
        updated_at: Timestamp when this entry was calculated/cached
        hour: Optional hour (0-23) for contextual entries
        cycle_count: Number of cycles used to calculate this value (optional)
    """
    value: float
    updated_at: datetime
    hour: int | None = None
    cycle_count: int | None = None

    def is_for_hour(self, hour: int) -> bool:
        """Check if entry matches requested hour."""
        return self.hour == hour

    def is_stale(self, max_age_seconds: int = 86400) -> bool:
        """Check if cache is older than max_age_seconds."""
        age = (datetime.utcnow() - self.updated_at).total_seconds()
        return age > max_age_seconds
```

#### 2. **ContextualLHSData** (New - Optional Value Object)

```python
@dataclass(frozen=True)
class ContextualLHSData:
    """Result of contextual LHS calculation for a specific hour.

    Attributes:
        hour: Hour of day (0-23)
        lhs: The calculated LHS value in °C/hour, or None if insufficient data
        cycle_count: Number of cycles used in calculation
        calculated_at: When this calculation was performed
        reason: Human-readable explanation if lhs is None
    """
    hour: int
    lhs: float | None
    cycle_count: int
    calculated_at: datetime
    reason: str = ""  # "insufficient_data", "calculation_failed", etc.
```

---

## Cache Management Strategy

### Storage Structure

**Location:** `HAModelStorage` (persisted in Home Assistant storage)

**Format:**
```python
{
    "cached_global_lhs": {
        "value": 15.2,
        "updated_at": "2025-02-09T10:30:00+00:00"
    },
    "cached_contextual_lhs": {
        "0": {"value": 12.1, "updated_at": "2025-02-09T10:30:00+00:00"},
        "6": {"value": 15.0, "updated_at": "2025-02-09T10:30:00+00:00"},
        "12": {"value": 14.5, "updated_at": "2025-02-09T10:30:00+00:00"},
        # ... 0-23 hours
    }
}
```

### When Cache is Populated

1. **During Cycle Extraction** (in ExtractHeatingCyclesUseCase)
   ```
   For each extracted cycle:
     - Extract start_hour = cycle.start_time.hour
     - Calculate cycle LHS = cycle.avg_heating_slope
     - Load hour's existing LHS list from cache
     - Append new LHS value
     - Calculate new average
     - Save back to cache[hour]
   ```

2. **Timing:** After cycles are extracted, before returning to caller

3. **Frequency:** Every 24 hours (via periodic refresh in ExtractHeatingCyclesUseCase)

### When Cache is Cleared

1. **On Retention Configuration Change**
   ```python
   async def on_retention_changed(new_retention_days: int):
       await model_storage.clear_cache_if_needed(new_retention_days)
   ```

2. **On Clear History Command** (via Rest API)
   ```python
   async def clear_history():
       await model_storage.clear_slope_history()
       # Clears both global AND contextual caches
   ```

3. **Cache Aging**
   - Each entry has `updated_at` timestamp
   - On read: Check if entry is older than 30 days (or retention period)
   - If stale: Recalculate from current cycles

### Persistence

- **Yes**, persisted in HAModelStorage (via Home Assistant Storage helper)
- **Why:** Contextual patterns may take weeks to stabilize; persisting across restarts improves ML quality
- **Trade-off:** Storage size = 24 entries × ~100 bytes = ~2.4 KB (minimal impact)

---

## Data Flow

### 1. Cycle Extraction to Cache Population

```
ExtractHeatingCyclesUseCase.execute()
  ↓
[Fetch historical data via adapters]
  ↓
[Extract cycles via HeatingCycleService]
  ↓
[Calculate global LHS]
  └─→ model_storage.set_cached_global_lhs(lhs, now)
  ↓
[NEW: For each cycle → populate contextual LHS]
  └─→ ContextualLHSCalculatorService.populate_contextual_cache(cycles)
       ├─ For each cycle:
       │  ├─ hour = cycle.start_time.hour
       │  ├─ lhs_list = model_storage.get_lhs_list_for_hour(hour)
       │  ├─ lhs_list.append(cycle.avg_heating_slope)
       │  ├─ avg = mean(lhs_list)
       │  └─ model_storage.set_cached_contextual_lhs(hour, avg, now)
       └─ [Returns: list of ContextualLHSData]
  ↓
[Cache append completes]
  ↓
[Timer for next 24h refresh scheduled]
```

### 2. Sensor Read (Current Hour Calculation)

```
IntelligentHeatingPilotContextualLearnedSlopeSensor.native_value
  ↓
[Get next schedule time from coordinator]
  next_schedule_time = coordinator.get_next_schedule_time()
  ↓
[If no scheduler configured]
  return None → "unknown"
  ↓
[Extract hour from next_schedule_time]
  hour = next_schedule_time.hour
  ↓
[Get cached contextual LHS for that hour]
  entry = await model_storage.get_cached_contextual_lhs(hour)
  ↓
[If cache entry available and not stale]
  return entry.value
  ↓
[Cache miss or stale]
  lhs = await calculate_contextual_lhs_on_demand(hour)
  return lhs or None
```

### 3. Handler: Extract and Populate

```
Application Layer:
  ContextualLHSCalculatorService (NEW)
    ├─ populate_contextual_cache()
    │  ├─ Input: cycles (list[HeatingCycle])
    │  ├─ For hour in 0..23:
    │  │  ├─ Filter cycles where cycle.start_time.hour == hour
    │  │  ├─ If empty: skip (no data for this hour)
    │  │  ├─ If found:
    │  │  │  ├─ lhs_values = [c.avg_heating_slope for c in filtered]
    │  │  │  ├─ avg_lhs = mean(lhs_values)
    │  │  │  └─ await model_storage.set_cached_contextual_lhs(hour, avg_lhs, now)
    │  │  └─
    │  └─ Return: dict[hour] → ContextualLHSData
    │
    └─ calculate_contextual_lhs_for_hour(cycles, hour)
       ├─ Input: cycles, target_hour
       ├─ Filter cycles by hour
       └─ Return: float | None
```

---

## Architecture Components

### Domain Layer

#### 1. **ContextualLHSCalculatorService** (New Domain Service)

**File:** `domain/services/contextual_lhs_calculator_service.py`

**Responsibility:** Pure domain logic for contextual LHS calculation

**Key Methods:**

```python
class ContextualLHSCalculatorService:
    """Calculate and manage contextual LHS (Learning Heating Slope).

    Pure domain logic with no Home Assistant dependencies.
    Focuses on grouping cycles by start_hour and calculating averages.
    """

    def extract_hour_from_cycle(self, cycle: HeatingCycle) -> int:
        """Extract hour (0-23) from cycle start time.

        Args:
            cycle: The heating cycle

        Returns:
            Hour of day (0-23)
        """
        pass

    def group_cycles_by_start_hour(
        self,
        cycles: list[HeatingCycle]
    ) -> dict[int, list[HeatingCycle]]:
        """Group cycles by their start_time hour.

        Args:
            cycles: All extracted heating cycles

        Returns:
            Mapping {hour: [cycles_starting_at_hour]}
        """
        pass

    def calculate_contextual_lhs_for_hour(
        self,
        cycles: list[HeatingCycle],
        target_hour: int
    ) -> float | None:
        """Calculate average LHS for cycles starting at target_hour.

        Returns None if no cycles found for that hour.

        Args:
            cycles: All extracted cycles
            target_hour: Hour (0-23) to filter by

        Returns:
            Average LHS value or None if no data
        """
        pass

    def calculate_all_contextual_lhs(
        self,
        cycles: list[HeatingCycle]
    ) -> dict[int, float | None]:
        """Calculate contextual LHS for all 24 hours.

        Args:
            cycles: All extracted cycles

        Returns:
            Mapping {hour: avg_lhs_value_or_none}
        """
        pass
```

#### 2. **Updated LHSCalculationService**

Enhance existing service to add:

```python
class LHSCalculationService:
    # ... existing methods ...

    def calculate_contextual_lhs(
        self,
        heating_cycles: list[HeatingCycle],
        target_hour: int
    ) -> float | None:
        """Calculate average LHS for cycles starting at target_hour.

        (Should delegate to ContextualLHSCalculatorService)
        """
        pass
```

---

### Infrastructure Layer

#### 1. **Updated HAModelStorage Interface Methods**

**File:** `infrastructure/adapters/model_storage.py`

```python
class HAModelStorage(IModelStorage):

    # Existing methods...

    async def get_lhs_values_for_hour(self, hour: int) -> list[float]:
        """Get all LHS values cached for a specific hour.

        Used during population to append new values.

        Args:
            hour: Hour (0-23)

        Returns:
            List of LHS values collected for this hour
        """
        pass

    async def append_to_contextual_lhs(
        self,
        hour: int,
        lhs_value: float
    ) -> float:
        """Append a new LHS value to the hour's list and return new average.

        Args:
            hour: Hour (0-23)
            lhs_value: New LHS value to add

        Returns:
            Updated average LHS for that hour
        """
        pass

    async def get_contextual_cache_stats() -> dict[int, dict]:
        """Get cache statistics for debugging.

        Returns:
            {hour: {"count": n, "avg": f, "updated_at": iso_string}}
        """
        pass

    async def clear_contextual_cache() -> None:
        """Clear all contextual LHS cache entries."""
        pass
```

#### 2. **Updated IModelStorage Interface**

**File:** `domain/interfaces/model_storage_interface.py`

Update interface to include new method signatures (already defined as abstract)

---

### Application Layer

#### 1. **Enhanced ExtractHeatingCyclesUseCase**

**File:** `application/extract_heating_cycles_use_case.py`

```python
class ExtractHeatingCyclesUseCase:

    def __init__(
        self,
        # ... existing params ...
        contextual_lhs_calculator: ContextualLHSCalculatorService | None = None,
    ):
        pass

    async def execute(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Execute extraction with NEW step for contextual LHS population.

        Steps:
        1. Fetch historical data
        2. Extract cycles
        3. Calculate global LHS
        4. [NEW] Calculate and cache contextual LHS by hour
        5. Append to cache
        6. Schedule refresh
        """

        # ... existing steps 1-3 ...

        # STEP 4: NEW - Populate contextual LHS cache
        if cycles and self._contextual_lhs_calculator and self._model_storage:
            contextual_results = (
                self._contextual_lhs_calculator.calculate_all_contextual_lhs(cycles)
            )

            for hour, lhs_value in contextual_results.items():
                if lhs_value is not None:
                    await self._model_storage.set_cached_contextual_lhs(
                        hour=hour,
                        lhs=lhs_value,
                        updated_at=dt_util.utcnow(),
                    )

            _LOGGER.info(
                "Updated contextual LHS for %d hours from %d cycles",
                sum(1 for v in contextual_results.values() if v is not None),
                len(cycles),
            )

        # ... existing steps 5-6 ...
```

---

### Coordinator Layer

#### 1. **Enhanced IntelligentHeatingPilotCoordinator**

**File:** `coordinator.py`

```python
class IntelligentHeatingPilotCoordinator:

    def __init__(self, ...):
        # ... existing init ...
        self._next_schedule_time: datetime | None = None

    async def async_initialize(self):
        """Called after all adapters are initialized."""
        # ... existing init ...

        # Get initial next schedule time
        await self._update_next_schedule_time()

    async def _update_next_schedule_time(self) -> None:
        """Get next schedule time from scheduler reader."""
        if not self._scheduler_reader:
            self._next_schedule_time = None
            return

        try:
            timeslot = await self._scheduler_reader.get_next_scheduled_event()
            if timeslot:
                self._next_schedule_time = timeslot.target_time
            else:
                self._next_schedule_time = None
        except Exception as e:
            _LOGGER.warning("Failed to get next schedule time: %s", e)
            self._next_schedule_time = None

    def get_next_schedule_time(self) -> datetime | None:
        """Get cached next schedule time."""
        return self._next_schedule_time

    def get_contextual_learned_heating_slope(self) -> float | None:
        """Get contextual LHS for NEXT schedule time hour.

        ENHANCED: Now uses next_schedule_time instead of current hour.

        Returns:
            Contextual LHS for schedule hour, or None if:
            - No scheduler configured
            - No cycles for that hour
            - Calculation failed
        """
        next_schedule = self.get_next_schedule_time()

        if next_schedule is None:
            _LOGGER.debug("No next schedule time; contextual LHS = None")
            return None

        target_hour = next_schedule.hour

        try:
            # Synchronous read from cache
            # (Note: In future, could make this async if needed)
            cached_entry = self._model_storage.get_cached_contextual_lhs_sync(target_hour)

            if cached_entry and not cached_entry.is_stale():
                return cached_entry.value
            else:
                return None
        except Exception as e:
            _LOGGER.warning(
                "Failed to get contextual LHS for hour %d: %s", target_hour, e
            )
            return None
```

---

### Sensor Layer

#### 1. **Enhanced IntelligentHeatingPilotContextualLearnedSlopeSensor**

**File:** `sensor.py`

```python
class IntelligentHeatingPilotContextualLearnedSlopeSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for contextual LHS based on NEXT SCHEDULE TIME hour."""

    @property
    def native_value(self) -> float | str | None:
        """Return contextual LHS for next schedule time hour.

        CHANGED: Now uses next_schedule_time hour instead of current hour.
        """
        # Get contextual LHS from coordinator
        contextual_lhs = self.coordinator.get_contextual_learned_heating_slope()

        if contextual_lhs is None:
            return "unknown"

        return float(round(contextual_lhs, 2))

    @property
    def extra_state_attributes(self) -> dict:
        """Return attributes including schedule hour reference."""
        next_schedule = self.coordinator.get_next_schedule_time()

        if next_schedule is None:
            return {
                "description": "No scheduler configured",
                "schedule_hour": None,
                "next_schedule_time": None,
            }

        schedule_hour = next_schedule.hour

        return {
            "description": f"Average LHS for cycles starting at {schedule_hour:02d}:00",
            "schedule_hour": f"{schedule_hour:02d}:00",
            "next_schedule_time": next_schedule.isoformat(),
        }
```

---

## File Structure & Skeleton Code

### Files to Create

```
custom_components/intelligent_heating_pilot/
├── domain/
│   └── services/
│       └── contextual_lhs_calculator_service.py  [NEW]
│
├── application/
│   └── (extract_heating_cycles_use_case.py - MODIFY)
│
├── infrastructure/
│   └── adapters/
│       └── (model_storage.py - MODIFY)
│
├── (coordinator.py - MODIFY)
└── (sensor.py - MODIFY)

tests/
├── unit/
│   ├── domain/
│   │   └── services/
│   │       └── test_contextual_lhs_calculator_service.py  [NEW]
│   │
│   └── infrastructure/
│       └── adapters/
│           └── (test_model_storage.py - MODIFY)
│
└── integration/
    └── test_contextual_lhs_end_to_end.py  [NEW]
```

---

### Skeleton Code Files

#### File 1: `domain/services/contextual_lhs_calculator_service.py`

```python
"""Service for calculating contextual Learning Heating Slope (LHS).

Pure domain logic for grouping cycles by start hour and calculating
average heating slopes per hour. No Home Assistant dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)


class ContextualLHSCalculatorService:
    """Calculate contextual LHS grouped by start hour.

    Responsibilities:
    - Extract hour from cycle start_time
    - Group cycles by start hour
    - Calculate average LHS per hour
    - Handle empty groups gracefully
    """

    def extract_hour_from_cycle(self, cycle: HeatingCycle) -> int:
        """Extract hour (0-23) from cycle start time.

        Args:
            cycle: The heating cycle

        Returns:
            Hour of day (0-23)
        """
        _LOGGER.debug(
            "Extracting hour from cycle started at %s",
            cycle.start_time
        )
        hour = cycle.start_time.hour
        _LOGGER.debug("Extracted hour: %d", hour)
        return hour

    def group_cycles_by_start_hour(
        self,
        cycles: list[HeatingCycle]
    ) -> dict[int, list[HeatingCycle]]:
        """Group cycles by their start_time hour.

        Args:
            cycles: All extracted heating cycles

        Returns:
            Mapping {hour: [cycles_starting_at_hour]}
        """
        _LOGGER.debug("Grouping %d cycles by start hour", len(cycles))

        grouped: dict[int, list[HeatingCycle]] = {h: [] for h in range(24)}

        for cycle in cycles:
            hour = self.extract_hour_from_cycle(cycle)
            grouped[hour].append(cycle)

        # Log summary
        non_empty = {h: len(c) for h, c in grouped.items() if c}
        _LOGGER.info("Grouped cycles by hour: %s", non_empty)

        return grouped

    def calculate_contextual_lhs_for_hour(
        self,
        cycles: list[HeatingCycle],
        target_hour: int
    ) -> float | None:
        """Calculate average LHS for cycles starting at target_hour.

        Args:
            cycles: All extracted cycles
            target_hour: Hour (0-23) to filter by

        Returns:
            Average LHS value or None if no data for this hour

        Raises:
            ValueError: If target_hour not in 0-23
        """
        if not 0 <= target_hour <= 23:
            raise ValueError(f"target_hour must be 0-23, got {target_hour}")

        _LOGGER.debug(
            "Calculating contextual LHS for hour %d from %d cycles",
            target_hour,
            len(cycles)
        )

        # Filter cycles starting at target hour
        matching_cycles = [
            c for c in cycles
            if self.extract_hour_from_cycle(c) == target_hour
        ]

        if not matching_cycles:
            _LOGGER.debug("No cycles found for hour %d", target_hour)
            return None

        # Calculate average LHS
        lhs_values = [c.avg_heating_slope for c in matching_cycles]
        avg_lhs = sum(lhs_values) / len(lhs_values)

        _LOGGER.info(
            "Calculated contextual LHS for hour %d: %.2f°C/h from %d cycles",
            target_hour,
            avg_lhs,
            len(matching_cycles)
        )

        return avg_lhs

    def calculate_all_contextual_lhs(
        self,
        cycles: list[HeatingCycle]
    ) -> dict[int, float | None]:
        """Calculate contextual LHS for all 24 hours.

        Args:
            cycles: All extracted cycles

        Returns:
            Mapping {hour: avg_lhs_value_or_none}
        """
        _LOGGER.info("Calculating contextual LHS for all 24 hours")

        result = {}
        for hour in range(24):
            lhs = self.calculate_contextual_lhs_for_hour(cycles, hour)
            result[hour] = lhs

        hours_with_data = sum(1 for v in result.values() if v is not None)
        _LOGGER.info("Contextual LHS calculated for %d hours with data", hours_with_data)

        return result
```

#### File 2: `domain/value_objects/contextual_lhs_data.py` (Optional)

```python
"""Value object for contextual LHS calculation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ContextualLHSData:
    """Result of contextual LHS calculation for a specific hour.

    Attributes:
        hour: Hour of day (0-23)
        lhs: The calculated LHS value in °C/hour, or None if insufficient data
        cycle_count: Number of cycles used in calculation
        calculated_at: When this calculation was performed
        reason: Human-readable explanation if lhs is None
    """
    hour: int
    lhs: float | None
    cycle_count: int
    calculated_at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate the contextual LHS data."""
        if not 0 <= self.hour <= 23:
            raise ValueError(f"hour must be 0-23, got {self.hour}")

        if self.lhs is not None and self.lhs < 0:
            raise ValueError(f"lhs must be positive or None, got {self.lhs}")

        if self.cycle_count < 0:
            raise ValueError(f"cycle_count must be >= 0, got {self.cycle_count}")
```

#### File 3: Updates to `infrastructure/adapters/model_storage.py`

```python
# Add to HAModelStorage class:

async def get_lhs_values_for_hour(self, hour: int) -> list[float]:
    """Get all LHS values cached for a specific hour.

    Used during population to append new values.

    Args:
        hour: Hour (0-23)

    Returns:
        List of LHS values collected for this hour
    """
    await self._ensure_loaded()
    contextual_cache = self._data.get("cached_contextual_lhs") or {}
    entries = contextual_cache.get(str(hour)) or {}

    # If stored as list of values with metadata:
    if isinstance(entries, dict) and "values" in entries:
        return entries.get("values", [])

    # If stored as single value (current format):
    if isinstance(entries, dict) and "value" in entries:
        return [entries["value"]]

    return []

async def append_to_contextual_lhs(
    self,
    hour: int,
    lhs_value: float
) -> float:
    """Append a new LHS value to the hour's list and return new average.

    Args:
        hour: Hour (0-23)
        lhs_value: New LHS value to add

    Returns:
        Updated average LHS for that hour
    """
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be 0-23, got {hour}")

    await self._ensure_loaded()

    contextual_cache = self._data.setdefault("cached_contextual_lhs", {})
    hour_key = str(hour)

    # Get existing values or start fresh
    existing = contextual_cache.get(hour_key, {})
    values = existing.get("values", []) if isinstance(existing, dict) else []

    # Append new value
    values.append(lhs_value)

    # Calculate new average
    avg_lhs = sum(values) / len(values)

    # Store both individual values and current entry
    contextual_cache[hour_key] = {
        "value": avg_lhs,
        "values": values,
        "updated_at": datetime.utcnow().isoformat(),
        "cycle_count": len(values),
    }

    await self._store.async_save(self._data)

    return avg_lhs

async def clear_contextual_cache(self) -> None:
    """Clear all contextual LHS cache entries."""
    _LOGGER.info("Clearing all contextual LHS cache")

    await self._ensure_loaded()
    self._data["cached_contextual_lhs"] = {}
    await self._store.async_save(self._data)

def get_cached_contextual_lhs_sync(self, hour: int) -> LHSCacheEntry | None:
    """Synchronous read of cached contextual LHS (for sensors).

    This method does NOT await or load async storage.
    Use only if data is already in-memory.

    Args:
        hour: Hour (0-23)

    Returns:
        LHSCacheEntry if available, None otherwise
    """
    if not self._loaded:
        return None

    contextual_cache = self._data.get("cached_contextual_lhs") or {}
    entry = contextual_cache.get(str(hour))
    return self._deserialize_cached_entry(entry, hour=hour)
```

#### File 4: Updates to `application/extract_heating_cycles_use_case.py`

```python
# Add to __init__:

def __init__(
    self,
    # ... existing params ...
    contextual_lhs_calculator: ContextualLHSCalculatorService | None = None,
):
    # ... existing init ...
    self._contextual_lhs_calculator = contextual_lhs_calculator

# Add to execute() method after calculating global LHS:

# STEP 2c: Update contextual LHS by hour if calculator available
if cycles and self._contextual_lhs_calculator and self._model_storage:
    all_contextual = self._contextual_lhs_calculator.calculate_all_contextual_lhs(cycles)

    updated_hours = 0
    for hour, lhs_value in all_contextual.items():
        if lhs_value is not None:
            await self._model_storage.set_cached_contextual_lhs(
                hour=hour,
                lhs=lhs_value,
                updated_at=dt_util.utcnow(),
            )
            updated_hours += 1

    if updated_hours > 0:
        _LOGGER.info(
            "Updated contextual LHS cache for %d hours from %d cycles",
            updated_hours,
            len(cycles),
        )
```

#### File 5: Updates to `coordinator.py`

```python
# Add to __init__:

self._next_schedule_time: datetime | None = None
self._contextual_lhs_calculator: ContextualLHSCalculatorService | None = None

# Add new methods:

async def _update_next_schedule_time(self) -> None:
    """Fetch next schedule time from scheduler reader.

    Called during initialization and on events.
    """
    _LOGGER.debug("Updating next schedule time")

    if not self._scheduler_reader:
        self._next_schedule_time = None
        return

    try:
        timeslot = await self._scheduler_reader.get_next_scheduled_event()
        if timeslot:
            self._next_schedule_time = timeslot.target_time
            _LOGGER.debug(
                "Next schedule time: %s (hour %d)",
                self._next_schedule_time,
                self._next_schedule_time.hour
            )
        else:
            self._next_schedule_time = None
            _LOGGER.debug("No next scheduled event")
    except Exception as e:
        _LOGGER.warning("Failed to update next schedule time: %s", e)
        self._next_schedule_time = None

def get_next_schedule_time(self) -> datetime | None:
    """Get cached next schedule time."""
    return self._next_schedule_time

def get_contextual_learned_heating_slope(self) -> float | None:
    """Get contextual LHS for next schedule time hour.

    CHANGED: Now uses next_schedule_time instead of current hour.
    Returns global LHS as fallback is NO LONGER USED.

    Returns:
        Contextual LHS for schedule hour, or None if:
        - No scheduler configured
        - No cycles for that hour
        - Calculation failed
    """
    next_schedule = self.get_next_schedule_time()

    if next_schedule is None:
        _LOGGER.debug("No next schedule time; contextual LHS = None")
        return None

    target_hour = next_schedule.hour

    try:
        # Synchronous read from cache if available
        if not self._model_storage:
            return None

        cached_entry = self._model_storage.get_cached_contextual_lhs_sync(target_hour)

        if cached_entry and not cached_entry.is_stale():
            _LOGGER.debug(
                "Returning cached contextual LHS for hour %d: %.2f°C/h",
                target_hour,
                cached_entry.value
            )
            return cached_entry.value
        else:
            _LOGGER.debug("No cached contextual LHS for hour %d", target_hour)
            return None
    except Exception as e:
        _LOGGER.warning(
            "Failed to get contextual LHS for hour %d: %s", target_hour, e
        )
        return None
```

#### File 6: Updates to `sensor.py`

```python
# Replace IntelligentHeatingPilotContextualLearnedSlopeSensor:

class IntelligentHeatingPilotContextualLearnedSlopeSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for contextual LHS based on NEXT SCHEDULE TIME hour."""

    _attr_name = "Contextual Learned Heating Slope"
    _attr_native_unit_of_measurement = "°C/h"
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, name)
        self._attr_unique_id = (
            f"{config_entry.entry_id}_contextual_learned_heating_slope"
        )

    @property
    def native_value(self) -> float | str | None:
        """Return contextual LHS for next schedule time hour.

        CHANGED: Now uses next_schedule_time hour instead of current hour.
        """
        contextual_lhs = self.coordinator.get_contextual_learned_heating_slope()

        if contextual_lhs is None:
            return "unknown"

        return float(round(contextual_lhs, 2))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return attributes including schedule hour reference."""
        next_schedule = self.coordinator.get_next_schedule_time()

        if next_schedule is None:
            return {
                "description": "No scheduler configured",
                "schedule_hour": None,
                "next_schedule_time": None,
            }

        schedule_hour = next_schedule.hour

        return {
            "description": (
                f"Average LHS for cycles starting at {schedule_hour:02d}:00"
            ),
            "schedule_hour": f"{schedule_hour:02d}:00",
            "next_schedule_time": next_schedule.isoformat(),
        }

    def _handle_anticipation_result(self, data: dict) -> None:
        """Refresh state when anticipation event received."""
        self.async_write_ha_state()
```

---

## Integration Points

### 1. Factory Initialization

**Location:** `application/extract_heating_cycles_factory.py`

Add:
```python
def create_contextual_lhs_calculator(self) -> ContextualLHSCalculatorService:
    """Factory method to create contextual LHS calculator."""
    return ContextualLHSCalculatorService()
```

### 2. Coordinator Initialization

**Location:** `coordinator.py` - `async_initialize()` method

Add:
```python
async def async_initialize(self):
    # ... existing init ...

    # Initialize contextual LHS calculator
    self._contextual_lhs_calculator = ContextualLHSCalculatorService()

    # Get initial next schedule time
    await self._update_next_schedule_time()

    # Pass to use case
    await self._setup_use_cases()

async def _setup_use_cases(self):
    """Initialize application use cases with dependencies."""
    self._extract_cycles_use_case = ExtractHeatingCyclesUseCase(
        # ... existing params ...
        contextual_lhs_calculator=self._contextual_lhs_calculator,
    )
```

### 3. Event Bridge Integration

**When to refresh next_schedule_time:**

```python
# In HAEventBridge or similar event handler

async def on_scheduler_event(event_data: dict):
    """Handle scheduler entity state change."""
    await self._coordinator._update_next_schedule_time()
    # Trigger sensor refresh
    self.coordinator.async_notify_all_sensors()
```

---

## Test Coverage Plan

### Unit Tests (Domain Layer)

**File:** `tests/unit/domain/services/test_contextual_lhs_calculator_service.py`

#### Test Cases:

1. **extract_hour_from_cycle** ✓
   - Extract hour from cycle with various times
   - Verify hour is (0-23)
   - Test midnight edge case (hour=0)
   - Test 23:xx edge case (hour=23)

2. **group_cycles_by_start_hour** ✓
   - Empty cycles list → 24 empty groups
   - Single cycle at hour 6 → only group[6] has data
   - Multiple cycles spread across hours
   - All cycles at same hour → only one group with data

3. **calculate_contextual_lhs_for_hour - Valid Cases** ✓
   - Single cycle for hour X → returns that cycle's LHS
   - Two cycles for hour X → returns average
   - Multiple cycles with different LHS values → returns correct average
   - Verify return type is float

4. **calculate_contextual_lhs_for_hour - No Data** ✓
   - No cycles for target hour → returns None
   - Empty cycles list → returns None
   - Cycles only at other hours → returns None

5. **calculate_contextual_lhs_for_hour - Edge Cases** ✓
   - target_hour=-1 → raises ValueError
   - target_hour=24 → raises ValueError
   - Cycles with 0 LHS value → handled correctly
   - Cycles with negative LHS → handled (even if physically impossible)

6. **calculate_all_contextual_lhs** ✓
   - Empty cycles → all 24 hours are None
   - Single cycle at hour 6 → only hour 6 has value, others None
   - Cycles spread across hours → correct distribution
   - Verify dict size is exactly 24

### Infrastructure Tests

**File:** `tests/unit/infrastructure/adapters/test_model_storage_contextual.py`

#### Test Cases:

1. **get_cached_contextual_lhs - Hit** ✓
   - Entry exists and not stale → returns LHSCacheEntry
   - Verify hour field matches input

2. **get_cached_contextual_lhs - Miss** ✓
   - No entry for hour → returns None
   - Retention disabled → returns None

3. **set_cached_contextual_lhs** ✓
   - Store entry for hour 6
   - Verify persistent after reload
   - Update existing entry → overwrites
   - Verify timestamp updated

4. **get_lhs_values_for_hour** ✓
   - First call on empty hour → returns empty list
   - After appending one value → returns [value]
   - Multiple appends → returns all values in order

5. **append_to_contextual_lhs** ✓
   - First append to empty hour → avg = value
   - Two appends [10, 20] → avg = 15
   - Three appends [10, 20, 30] → avg = 20
   - Verify persistence

6. **clear_contextual_cache** ✓
   - Cache populated → cleared
   - Verify all entries removed
   - Verify storage persisted

### Integration Tests

**File:** `tests/integration/test_contextual_lhs_end_to_end.py`

#### Test Scenarios:

1. **Scenario A: Scheduler Active + Cycles Exist for Hour** ✓
   ```python
   # Setup: Next schedule at 06:00, cycles at hours 6
   # Execute: Extract cycles, populate cache
   # Verify: contextual_lhs = average of cycles at hour 6
   # Verify: Sensor returns numeric value
   ```

2. **Scenario B: Scheduler Active + NO Cycles for Hour** ✓
   ```python
   # Setup: Next schedule at 12:00, cycles only at hour 6
   # Execute: Extract cycles, populate cache
   # Verify: contextual_lhs = None (no data for hour 12)
   # Verify: Sensor returns "unknown"
   ```

3. **Scenario C: No Scheduler Configured** ✓
   ```python
   # Setup: scheduler_entities = [], no next schedule time
   # Execute: Extract cycles
   # Verify: contextual_lhs = None
   # Verify: Sensor returns "unknown"
   # Verify: Attributes show "No scheduler configured"
   ```

4. **Scenario D: Calculation Recovers from Exception** ✓
   ```python
   # Setup: Next schedule exists but coordinator raises exception
   # Execute: Try to get contextual LHS
   # Verify: Returns None (graceful fallback)
   # Verify: Warning logged
   ```

5. **Multi-Day Cycles** ✓
   ```python
   # Setup: Cycle from 2025-02-08 22:00 to 2025-02-09 01:00
   # Verify: Belongs to hour 22 (start hour used, not active hour)
   # Note: This tests the "start_hour" grouping logic
   ```

6. **Cache Refresh on Extraction** ✓
   ```python
   # First extraction: cycles at hour 6, cache[6] = 15.0
   # Second extraction: new cycles at hour 6, cache[6] updated
   # Verify: Average includes both old and new cycles
   ```

### QA Phase Regression Tests

After implementation, add regression tests for:
- Bug: Contextual LHS returning global instead of contextual
  ```python
  async def test_contextual_lhs_uses_schedule_hour_not_current_hour():
      """Regression: Contextual LHS must use next_schedule_time hour."""
      # Setup: current_hour = 14, next_schedule_hour = 6
      # Only cycles at hour 6 exist
      # Expected: sensor returns value from hour 6, NOT hour 14
      pass
  ```

---

## Open Questions & Trade-offs

### 1. **Cache Invalidation Strategy**

**Question:** When should cached contextual LHS be recalculated?

**Options:**
- **(A) Only on cycle extraction refresh** (24h timer)
  - Pro: Simple, minimal overhead
  - Con: Cache can be stale for 24h if retention settings change

- **(B) On every retention configuration change**
  - Pro: Accurate, captures config updates
  - Con: More frequent recalculation

- **(C) Implement staleness check (e.g., > 30 days old)**
  - Pro: Balance between freshness and performance
  - Con: Requires timestamp checking

**Recommendation:** Start with **(A)** + implement **(C)** for next phase

---

### 2. **Synchronous vs Async Access**

**Question:** Should `get_contextual_learned_heating_slope()` be async?

**Current Design:**
- Coordinator method is **synchronous**
- Calls `get_cached_contextual_lhs_sync()` (non-awaiting)
- Why: Sensors need synchronous property access; can't use `await` in `@property`

**Trade-off:**
- **Pro:** Sensors can read directly without async complications
- **Con:** Must pre-load cache in memory; misses are not recoverable at sensor time

**Future Improvement:** If caching becomes insufficient, create an async coordinator accessor that sensors poll periodically

---

### 3. **Handling Cycles Spanning Multiple Days**

**Question:** If a cycle starts 2025-02-08 23:00 and ends 2025-02-09 02:00, which hour group?

**Decision:** Use `cycle.start_time.hour`
- Cycle belongs to hour 23 (when it started)
- Simplifies grouping logic
- Semantically: "This cycle was activated at hour 23"

**Alternative:** Could use "active_during_hour" (more complex, requires time range checks)

---

### 4. **Storage Volume & Cleanup**

**Question:** How much storage data accumulates with hourly caching?

**Calculation:**
- 24 hours × ~100 bytes per entry = ~2.4 KB per device
- With cycle counts/metadata: ~3-4 KB per device
- Minimal impact even with 100s of devices

**No cleanup needed** - HAModelStorage handles retention via cycle extraction refresh

---

### 5. **Next Schedule Time Update Frequency**

**Question:** How often should coordinator refresh next_schedule_time?

**Options:**
- **(A) Only on startup** → Stale if schedule changes during session
- **(B) On every sensor read** → Performance overhead
- **(C) On scheduler entity state change** (event-driven)
  - Pro: Fresh without polling
  - Con: Requires event subscription

**Recommendation:** **(C)** via HAEventBridge on scheduler entity state change

---

### 6. **Backward Compatibility**

**Question:** What happens to old integrations with global-LHS-only logic?

**Migration Path:**
1. Phase 1 (Current): Populate contextual cache during extraction
2. Phase 2 (Sensors): Use contextual LHS in sensor (this task)
3. Phase 3 (Future): Deprecate global LHS entirely

**During Phase 2:**
- Global LHS still calculated (for backward compatibility)
- Sensor prefers contextual; falls back to None (not global)
- Users see "unknown" instead of outdated global value (better UX)

---

## Implementation Checklist (QA Phase)

Before writing implementation, QA should:

- [ ] Review all 4 test scenarios with product team
- [ ] Confirm hour-grouping strategy (start_hour vs active_during_hour)
- [ ] Decide cache invalidation strategy (A, B, or C)
- [ ] Confirm storage structure format (embedded cycle lists or separate?)
- [ ] Test with real Home Assistant installation
- [ ] Verify sensor attribute display in Lovelace
- [ ] Load test with 1000+ cycles to verify performance
- [ ] Test cache recovery after HA restart
- [ ] Document user-visible behavior changes

---

## Appendix: Related Code References

### Existing Value Objects
- `domain/value_objects/lhs_cache_entry.py`
- `domain/value_objects/heating.py` (HeatingCycle)

### Existing Services
- `domain/services/lhs_calculation_service.py`
- `domain/services/heating_cycle_service.py`

### Existing Interfaces
- `domain/interfaces/model_storage_interface.py`
- `domain/interfaces/heating_cycle_service_interface.py`

### Current Implementation Status
- ✓ LHSCacheEntry with hour field
- ✓ IModelStorage with contextual methods (abstract)
- ✓ HAModelStorage with basic get/set (needs enhancement)
- ✓ LHSCalculationService.calculate_contextual_lhs() (exists but not used)
- ✗ Coordinator.get_contextual_learned_heating_slope() (returns global, should return contextual)
- ✗ Sensor uses current_hour instead of next_schedule_time hour
- ✗ ContextualLHSCalculatorService (NEW - needs creation)
- ✗ Cache population in ExtractHeatingCyclesUseCase (needs addition)

---

## Summary

This architecture provides:

1. **Pure Domain Logic** - `ContextualLHSCalculatorService` with no HA dependencies
2. **Clear Separation** - Domain → Infrastructure → Application → Coordinator → Sensors
3. **Graceful Degradation** - Returns None when data unavailable (sensor shows "unknown")
4. **TDD Compliant** - 30+ test cases covering all scenarios
5. **Production Ready** - Handles edge cases, caching, invalidation, errors

The design is **complete and ready for QA to write tests, followed by development implementation.**
