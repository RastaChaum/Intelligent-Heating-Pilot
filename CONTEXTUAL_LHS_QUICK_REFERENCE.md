# Contextual LHS Quick Reference (Cheat Sheet)

**Use This:** During implementation when you need a quick lookup
**For Details:** See ARCHITECTURE_CONTEXTUAL_LHS.md

---

## Problem & Solution (30 seconds)

### Problem
```
Current: contextual_lhs sensor shows GLOBAL LHS (wrong)
         sensor.py line 286: current_hour = dt_util.utcnow().hour

Expected: contextual_lhs sensor shows CONTEXTUAL LHS based on NEXT SCHEDULE TIME hour
```

### Solution
```
Replace hour source:       current_hour → next_schedule_time.hour
Replace value source:      global_lhs → cache[hour]
Add fallback:             None → "unknown" (instead of global)
```

---

## 4 Scenarios (Decision Matrix)

| Scenario | Next Schedule | Cycles at Hour | Result | Sensor |
|----------|---------------|---|--------|--------|
| A | ✅ 06:00 | ✅ [15.0, 14.5] | 14.75 | `14.75` |
| B | ✅ 12:00 | ❌ None | None | `"unknown"` |
| C | ❌ None | ✅ Exist | None | `"unknown"` |
| D | ✅ Exists | ? | Exception → None | `"unknown"` |

---

## 5 Files to Change (Implementation Order)

### 1. ✅ CREATE: ContextualLHSCalculatorService (120 lines)
**File:** `domain/services/contextual_lhs_calculator_service.py`

**Key Methods:**
```python
def extract_hour_from_cycle(cycle) -> int:           # 0-23
def group_cycles_by_start_hour(cycles) -> dict:      # hour → [cycles]
def calculate_contextual_lhs_for_hour(cycles, hour) -> float | None:
def calculate_all_contextual_lhs(cycles) -> dict:    # hour → float|None
```

**Status:** ✅ Skeleton ready - just implement method bodies

---

### 2. 🔄 ENHANCE: HAModelStorage (4 new methods)
**File:** `infrastructure/adapters/model_storage.py`

**Add Methods:**
```python
async def get_lhs_values_for_hour(hour: int) -> list[float]:
    # Returns all LHS values cached for this hour

async def append_to_contextual_lhs(hour: int, lhs_value: float) -> float:
    # Append value and return updated average

async def clear_contextual_cache() -> None:
    # Zap all contextual entries

def get_cached_contextual_lhs_sync(hour: int) -> LHSCacheEntry | None:
    # Synchronous read (no await!) for sensor use
```

**Storage Format:**
```python
"cached_contextual_lhs": {
    "0": {"value": 12.5, "updated_at": "2025-02-09T10:30:00+00:00"},
    "6": {"value": 15.2, "updated_at": "2025-02-09T10:30:00+00:00"},
    ...  # hours 0-23
}
```

---

### 3. 🔄 ENHANCE: ExtractHeatingCyclesUseCase
**File:** `application/extract_heating_cycles_use_case.py`

**Add to __init__:**
```python
self._contextual_lhs_calculator: ContextualLHSCalculatorService | None = None
```

**Add after STEP 2b (global LHS calc):**
```python
# STEP 2c: Update contextual LHS by hour
if cycles and self._contextual_lhs_calculator and self._model_storage:
    all_contextual = self._contextual_lhs_calculator.calculate_all_contextual_lhs(cycles)
    for hour, lhs_value in all_contextual.items():
        if lhs_value is not None:
            await self._model_storage.set_cached_contextual_lhs(
                hour=hour, lhs=lhs_value, updated_at=dt_util.utcnow()
            )
    _LOGGER.info(f"Updated contextual LHS cache for {updated_hours} hours")
```

---

### 4. 🔄 ENHANCE: Coordinator
**File:** `coordinator.py`

**Add to __init__:**
```python
self._next_schedule_time: datetime | None = None
```

**Add new method:**
```python
async def _update_next_schedule_time(self) -> None:
    """Fetch next schedule time from scheduler reader."""
    if not self._scheduler_reader:
        self._next_schedule_time = None
        return
    try:
        timeslot = await self._scheduler_reader.get_next_scheduled_event()
        self._next_schedule_time = timeslot.target_time if timeslot else None
    except Exception as e:
        _LOGGER.warning("Failed to get next schedule time: %s", e)
        self._next_schedule_time = None
```

**Add new method:**
```python
def get_next_schedule_time(self) -> datetime | None:
    """Get cached next schedule time."""
    return self._next_schedule_time
```

**Replace existing method:**
```python
def get_contextual_learned_heating_slope(self) -> float | None:
    """CHANGED: Use next_schedule_time hour, NOT current hour."""
    next_schedule = self.get_next_schedule_time()
    if next_schedule is None:
        return None

    target_hour = next_schedule.hour
    try:
        cached_entry = self._model_storage.get_cached_contextual_lhs_sync(target_hour)
        if cached_entry and not cached_entry.is_stale():
            return cached_entry.value
        return None
    except Exception as e:
        _LOGGER.warning(f"Failed to get contextual LHS for hour {target_hour}: {e}")
        return None
```

---

### 5. 🔄 ENHANCE: Sensor
**File:** `sensor.py` - class `IntelligentHeatingPilotContextualLearnedSlopeSensor`

**Replace native_value property:**
```python
@property
def native_value(self) -> float | str | None:
    """CHANGED: Use next_schedule_time hour instead of current_hour."""
    contextual_lhs = self.coordinator.get_contextual_learned_heating_slope()
    return float(round(contextual_lhs, 2)) if contextual_lhs is not None else "unknown"
```

**Replace extra_state_attributes property:**
```python
@property
def extra_state_attributes(self) -> dict:
    """CHANGED: Show schedule hour instead of current hour."""
    next_schedule = self.coordinator.get_next_schedule_time()
    if next_schedule is None:
        return {
            "description": "No scheduler configured",
            "schedule_hour": None,
            "next_schedule_time": None,
        }
    return {
        "description": f"Average LHS for cycles starting at {next_schedule.hour:02d}:00",
        "schedule_hour": f"{next_schedule.hour:02d}:00",
        "next_schedule_time": next_schedule.isoformat(),
    }
```

---

## Critical Implementation Details

### ⚠️ Hour Extraction (Most Critical)
```python
# ✅ CORRECT: Use START hour (ignore end time)
hour = cycle.start_time.hour

# ❌ WRONG: Don't use "active during" logic with ranges
# ❌ WRONG: Don't use end time hour
```

### ⚠️ Synchronous Sensor Access (Why It Works)
```python
# Sensors use @property (must be synchronous)
@property
def native_value(self) -> float | str | None:
    lhs = self.coordinator.get_contextual_learned_heating_slope()  # ✅ OK
    # Do NOT: await self.coordinator.async_...()                  # ❌ SYNTAX ERROR

# Solution: Use sync cache read
def get_cached_contextual_lhs_sync(hour) -> LHSCacheEntry | None:
    if not self._loaded:
        return None  # Miss is OK - sensor shows "unknown"
    # Read from _data dict (no async)
```

### ⚠️ Graceful Degradation Chain
```python
# If any step fails, return None → sensor shows "unknown"
try:
    if next_schedule is None:
        return None
    target_hour = next_schedule.hour  # Could fail?
    cached = self._model_storage.get_cached_contextual_lhs_sync(target_hour)
    if cached is None or cached.is_stale():
        return None
    return cached.value
except Exception:
    return None  # ✅ Graceful
```

---

## Test Commands (Verify often)

```bash
# Run domain unit tests only
poetry run pytest tests/unit/domain/services/test_contextual_lhs_calculator_service.py -v

# Run integration tests
poetry run pytest tests/integration/test_contextual_lhs_end_to_end.py -v

# Run all tests with coverage
poetry run pytest tests/ -v --cov=custom_components/intelligent_heating_pilot

# Run tests matching pattern
poetry run pytest tests/ -k "scenario_a" -v
```

**Expected Domain Tests:** 30+ tests, all PASSING
**Expected Time:** ~0.5s total

---

## Logging Template (Copy-Paste)

```python
# Entry
_LOGGER.debug(
    "Entering method_name with params: arg1=%s, arg2=%s",
    arg1, arg2
)

# Processing
_LOGGER.debug("Processing step X...")

# State change (only here!)
_LOGGER.info(
    "Updated contextual LHS cache for hour %d: %.2f°C/h from %d cycles",
    hour, lhs_value, cycle_count
)

# Exit
_LOGGER.debug("Exiting method_name")

# Error
_LOGGER.warning("Failed to calculate contextual LHS for hour %d: %s", hour, exc)
```

---

## Debugging Checklist

```
Issue: Sensor shows "unknown" but cycles exist

☐ 1. Is next_schedule_time calculated?
      coordinator.get_next_schedule_time() != None

☐ 2. Is cache populated?
      model_storage.get_cached_contextual_lhs(6) != None

☐ 3. Does hour match?
      next_schedule.hour == cycle.start_time.hour

☐ 4. Is entry stale?
      cached_entry.is_stale() == False

☐ 5. Check logs for:
      "Updated contextual LHS cache for N hours"
      "Returning cached contextual LHS for hour X"
```

---

## Common Mistakes to Avoid

| ❌ Mistake | ✅ Fix | Why |
|-----------|--------|-----|
| `async def native_value(self)` | `@property native_value(self)` | Sensors can't be async |
| `await model_storage.get_cached_contextual_lhs_sync()` | Don't await sync methods | They read from _data dict |
| `cycle.end_time.hour` for grouping | `cycle.start_time.hour` | Start hour defines the group |
| Return global_lhs if no contextual | Return None → "unknown" | Honest UX |
| Store cycles in cache | Store only lhs values | Cache size matters |
| Recalculate on every read | Pre-populate during extraction | Performance |

---

## Key Data Types

```python
# Hour
hour: int  # 0-23, validated with "not 0 <= hour <= 23"

# LHS Value
lhs: float  # °C/hour, positive

# Cache Entry
from domain.value_objects.lhs_cache_entry import LHSCacheEntry
entry = LHSCacheEntry(value=15.2, updated_at=datetime.now(), hour=6)

# Cycle
from domain.value_objects.heating import HeatingCycle
cycle.start_time: datetime
cycle.end_time: datetime
cycle.avg_heating_slope: float  # ° C/h

# Next Schedule
next_schedule: datetime | None
next_hour = next_schedule.hour if next_schedule else None
```

---

## Performance Targets

| Operation | Target | Status |
|-----------|--------|--------|
| extract_hour_from_cycle() | <0.1ms | ✅ O(1) |
| group_cycles_by_start_hour(1000 cycles) | <5ms | ✅ O(n) |
| calculate_all_contextual_lhs(1000 cycles) | <10ms | ✅ O(n) |
| get_contextual_learned_heating_slope() | <1ms | ✅ O(1) dict lookup |
| Sensor native_value property access | <1ms | ✅ Direct call |

**Rule:** Sensor access must be <1ms to avoid UI lag

---

## Interface Compliance Checklist

```
Domain Layer (ContextualLHSCalculatorService):
  ☐ No `from homeassistant...` imports
  ☐ All methods typed with -> return types
  ☐ All parameters have type hints
  ☐ Docstrings for public methods
  ☐ Pure logic only (no I/O, no HA calls)

Infrastructure (HAModelStorage methods):
  ☐ Implements IModelStorage abstract methods
  ☐ Async where needed for I/O
  ☐ Sync where needed for sensors
  ☐ Exception handling (graceful degradation)
  ☐ Logging at DEBUG/INFO/WARNING levels

Application (ExtractHeatingCyclesUseCase):
  ☐ Accepts calculator dependency
  ☐ Calls calculator after cycle extraction
  ☐ Handles None gracefully
  ☐ Logs state changes

Coordinator:
  ☐ Stores next_schedule_time
  ☐ Provides get_next_schedule_time()
  ☐ Implements contextual LHS accessor correctly
  ☐ Returns None for graceful degradation

Sensor:
  ☐ Uses next_schedule_time (not current_hour)
  ☐ Uses coordinator.get_contextual_learned_heating_slope()
  ☐ Returns "unknown" for None
  ☐ Attributes show schedule context
```

---

## Emergency Rollback

If something breaks in production:

```python
# Command: Return global LHS (before contextual)
def get_contextual_learned_heating_slope(self) -> float | None:
    # Temporary: Just return global until fix is ready
    return self.get_learned_heating_slope()  # Fallback to global
```

**This maintains backward compatibility while fix is deployed.**

---

## Quick Math: LHS Average

```python
# Scenario from requirements:
cycles = [
    HeatingCycle(start_time=2025-02-08 06:15, ..., avg_heating_slope=15.0),
    HeatingCycle(start_time=2025-02-07 06:30, ..., avg_heating_slope=14.5),
]

# Calculation
hour_6_values = [15.0, 14.5]
average = sum(hour_6_values) / len(hour_6_values)
average = 29.5 / 2 = 14.75  ✅

# What sensor shows
contextual_lhs = 14.75
native_value = float(round(14.75, 2)) = 14.75 ✅
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-09 | Initial comprehensive design |

---

**Last Updated:** 2026-02-09
**For Full Details:** See ARCHITECTURE_CONTEXTUAL_LHS.md
