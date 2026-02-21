# Contextual LHS Implementation Guide

**Target Audience:** Development Team
**Phase:** Implementation (after QA tests written)
**Status:** Ready for Development

---

## Quick Start: What to Implement

### Phase 1: Domain Layer (Pure Logic)

1. **ContextualLHSCalculatorService** ✅ Skeleton created
   - File: `domain/services/contextual_lhs_calculator_service.py`
   - Status: Ready for implementation
   - No Home Assistant dependencies

2. **ContextualLHSData** ✅ Skeleton created
   - File: `domain/value_objects/contextual_lhs_data.py`
   - Status: Ready for implementation
   - Optional value object for results

### Phase 2: Infrastructure Adaptations

1. **HAModelStorage** - Enhance existing
   - File: `infrastructure/adapters/model_storage.py`
   - Add methods from design doc (Line ~150-200)
   - Implement cache get/set/append operations
   - Add synchronous read for sensors

2. **IModelStorage Interface** - Already defined
   - File: `domain/interfaces/model_storage_interface.py`
   - Methods already exist as abstract (no changes needed)

### Phase 3: Application Layer

1. **ExtractHeatingCyclesUseCase** - Enhance existing
   - File: `application/extract_heating_cycles_use_case.py`
   - Add contextual calculator dependency
   - Add cache population step in execute()
   - Lines to add: ~10 lines after global LHS calculation

### Phase 4: Coordinator Integration

1. **IntelligentHeatingPilotCoordinator** - Enhance existing
   - File: `coordinator.py`
   - Add `_next_schedule_time` field
   - Add `_update_next_schedule_time()` method
   - Update `get_contextual_learned_heating_slope()` implementation
   - Add `get_next_schedule_time()` accessor

### Phase 5: Sensor Updates

1. **IntelligentHeatingPilotContextualLearnedSlopeSensor** - Enhance existing
   - File: `sensor.py`
   - Change `native_value` property to use `next_schedule_time` hour
   - Update `extra_state_attributes` to show schedule context
   - No change to event handling

---

## Implementation Order (Recommended)

```
1. Implement ContextualLHSCalculatorService
   └─ Run unit tests (test_contextual_lhs_calculator_service.py)
   └─ Verify all 30+ unit tests pass

2. Enhance HAModelStorage
   └─ Add cache methods
   └─ Test persistence and retrieval

3. Update ExtractHeatingCyclesUseCase
   └─ Integrate calculator
   └─ Populate cache during extraction
   └─ Test cycle extraction flow

4. Update Coordinator
   └─ Add next_schedule_time tracking
   └─ Update get_contextual_learned_heating_slope()
   └─ Subscribe to scheduler changes

5. Update Sensor
   └─ Change hour source from current → schedule
   └─ Update attributes
   └─ Test end-to-end (integration tests)

6. Run full test suite
   └─ All unit tests
   └─ All integration tests
   └─ Manual HA testing with screenshots
```

---

## Code Snippets for Copy-Paste

### 1. Adding to ExtractHeatingCyclesUseCase.__init__

```python
def __init__(
    self,
    device_config: DeviceConfig,
    heating_cycle_service: IHeatingCycleService,
    historical_adapters: list[IHistoricalDataAdapter],
    cycle_cache: ICycleCache | None = None,
    timer_scheduler: ITimerScheduler | None = None,
    model_storage: IModelStorage | None = None,
    lhs_calculation_service: LHSCalculationService | None = None,
    contextual_lhs_calculator: ContextualLHSCalculatorService | None = None,  # NEW
) -> None:
    # ... existing init ...
    self._contextual_lhs_calculator = contextual_lhs_calculator  # NEW
```

### 2. Cache Population in ExtractHeatingCyclesUseCase.execute()

Add after STEP 2b (global LHS calculation):

```python
# STEP 2c: Update contextual LHS by hour
if cycles and self._contextual_lhs_calculator and self._model_storage:
    all_contextual = (
        self._contextual_lhs_calculator.calculate_all_contextual_lhs(cycles)
    )

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

### 3. Adding to Coordinator.__init__

```python
def __init__(self, hass: HomeAssistant, device_config: DeviceConfig) -> None:
    # ... existing init ...
    self._next_schedule_time: datetime | None = None  # NEW
    self._contextual_lhs_calculator: ContextualLHSCalculatorService | None = None  # NEW
```

### 4. New Coordinator Methods

```python
async def _update_next_schedule_time(self) -> None:
    """Fetch and cache next schedule time from scheduler reader."""
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

    CHANGED: No longer returns global LHS as fallback.
    Returns None if no data available.
    """
    next_schedule = self.get_next_schedule_time()

    if next_schedule is None:
        _LOGGER.debug("No next schedule time; contextual LHS = None")
        return None

    target_hour = next_schedule.hour

    try:
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

### 5. Updated Sensor native_value

```python
@property
def native_value(self) -> float | str | None:
    """Return contextual LHS for next schedule time hour."""
    contextual_lhs = self.coordinator.get_contextual_learned_heating_slope()

    if contextual_lhs is None:
        return "unknown"

    return float(round(contextual_lhs, 2))
```

### 6. Updated Sensor Attributes

```python
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
```

---

## Testing During Implementation

### Run Domain Tests

```bash
poetry run pytest tests/unit/domain/services/test_contextual_lhs_calculator_service.py -v
```

**Expected Output:**
```
test_extract_hour_at_midnight PASSED
test_extract_hour_at_morning PASSED
test_extract_hour_at_evening PASSED
test_group_empty_cycles_list PASSED
test_group_single_cycle_at_hour_6 PASSED
[... 25+ more tests ...]

============= 30 passed in 0.45s =============
```

### Run Integration Tests

```bash
poetry run pytest tests/integration/test_contextual_lhs_end_to_end.py -v
```

### Run All Tests

```bash
poetry run pytest tests/ -v --tb=short
```

---

## Debugging Checklist

### If Domain Tests Fail

1. Check `extract_hour_from_cycle()` - must return int in 0-23
2. Check `group_cycles_by_start_hour()` - must return dict[0..23]
3. Check `calculate_contextual_lhs_for_hour()` handles:
   - ValueError for invalid hours
   - None when no matching cycles
   - float average when cycles exist

### If Cache Operations Fail

1. Verify storage key format: `cached_contextual_lhs[str(hour)]`
2. Verify serialization: `{"value": float, "updated_at": iso_str}`
3. Verify async/sync boundary: `get_cached_contextual_lhs_sync()` must NOT await

### If Sensor Shows Wrong Value

1. Check `get_next_schedule_time()` returns correct datetime
2. Check coordinator passed to sensor
3. Check sensor calls `coordinator.get_contextual_learned_heating_slope()`
4. Check cache was populated: verify logs at INFO level

### If No Data in Cache

1. Logs should show "Updated contextual LHS cache for N hours"
2. If missing, use coordinator logs to trace cache population
3. Verify `set_cached_contextual_lhs()` is being called

---

## Integration with Existing Code

### Factory

**File:** `application/extract_heating_cycles_factory.py`

Add factory method:
```python
def create_contextual_lhs_calculator(self) -> ContextualLHSCalculatorService:
    """Factory for contextual LHS calculator."""
    return ContextualLHSCalculatorService()
```

### Coordinator Setup

**File:** `coordinator.py` - async_initialize() method

Add initialization:
```python
async def async_initialize(self) -> None:
    # ... existing init ...

    # Initialize contextual LHS calculator
    self._contextual_lhs_calculator = ContextualLHSCalculatorService()

    # Get initial next schedule time
    await self._update_next_schedule_time()
```

### Event Bridge

**File:** `infrastructure/event_bridge.py`

When scheduler changes, call:
```python
await coordinator._update_next_schedule_time()
self.coordinator.async_notify_all_sensors()
```

---

## Key Implementation Notes

### 1. Hour Extraction Logic

```python
hour = cycle.start_time.hour  # Always use START hour
# NOT: The hour when cycle ended
# NOT: Hours when cycle was active (would need range logic)
```

### 2. Cache Format

```
Storage Structure:
{
  "cached_contextual_lhs": {
    "0": {"value": 12.5, "updated_at": "2025-02-09T10:30:00+00:00"},
    "6": {"value": 15.2, "updated_at": "2025-02-09T10:30:00+00:00"},
    ...
  }
}
```

### 3. Synchronous Access from Sensor

```python
# Sensor property CANNOT use await
@property
def native_value(self) -> float | str | None:
    # This must be synchronous!
    lhs = self.coordinator.get_contextual_learned_heating_slope()
    return lhs or "unknown"

# Required: Use get_cached_contextual_lhs_sync() NOT get_cached_contextual_lhs()
def get_cached_contextual_lhs_sync(self, hour: int) -> LHSCacheEntry | None:
    # No await! No async_ensure_loaded()!
    # Must read from already-loaded _data dict
    if not self._loaded:
        return None
    # ... read from _data
```

### 4. Logging Standards

```python
_LOGGER.debug("Entering ...")           # Method entry
_LOGGER.debug("Exiting ...")            # Method exit
_LOGGER.info("Updated cache for hour 6 from 3 cycles")  # STATE CHANGES
_LOGGER.warning("No cached LHS for hour 12")  # Warnings
_LOGGER.error("Failed to populate cache: %s", exc)  # Errors
```

### 5. Error Handling

```python
# Always graceful degradation
try:
    lhs = self.get_contextual_learned_heating_slope()
except Exception as e:
    _LOGGER.warning("Failed to get contextual LHS: %s", e)
    return None  # Sensor shows "unknown"
```

---

## Performance Considerations

### Memory Impact
- 24 hours × ~100 bytes/entry = ~2.4 KB per device
- Minimal overhead

### Computation Impact
- `calculate_all_contextual_lhs()`: O(cycles × 24) ≈ O(n)
- Runs once per 24h refresh
- No impact on real-time performance

### Storage I/O
- `set_cached_contextual_lhs()` writes to HA storage once per hour max
- Async operation, doesn't block coordinator
- One write per 24h refresh cycle

---

## Troubleshooting

### Sensor Shows "unknown" but cycles exist

**Debugger:**
1. Check next_schedule_time is set
   ```python
   # In coordinator
   print(f"Next schedule: {self._next_schedule_time}")
   ```

2. Check cache was populated
   ```python
   # In model_storage
   await model_storage.get_cached_contextual_lhs(6)
   ```

3. Check hour matches
   ```python
   # Verify schedule_hour == cycle_hour
   schedule_hour = next_schedule_time.hour
   cycle_hour = cycle.start_time.hour
   ```

### Cache cleared unexpectedly

**Causes:**
- Retention configuration changed → `clear_contextual_cache()` called
- Clear history command executed
- HA restart with stale persistent storage

**Resolution:**
- Check logs for "Clearing all contextual LHS cache"
- Next 24h refresh will repopulate

### Type errors in tests

**If test imports fail:**
```bash
poetry install  # Reinstall dependencies
poetry run pytest tests/ --collect-only  # Verify imports
```

---

## Completion Checklist

### Code Implementation
- [ ] ContextualLHSCalculatorService - all methods implemented
- [ ] ContextualLHSData - value object complete
- [ ] HAModelStorage - cache methods implemented
- [ ] ExtractHeatingCyclesUseCase - cache population added
- [ ] Coordinator - next_schedule_time tracking added
- [ ] Coordinator - get_contextual_learned_heating_slope() updated
- [ ] Sensor - native_value uses next_schedule_time
- [ ] Sensor - attributes show schedule context

### Testing
- [ ] All unit tests pass (30+)
- [ ] All integration tests pass (8+)
- [ ] Code coverage > 80% for domain layer
- [ ] Manual HA testing with 10+ cycles

### Documentation
- [ ] Docstrings for all public methods
- [ ] Type hints complete
- [ ] Logging at appropriate levels

### Quality Assurance
- [ ] No new pylint/mypy errors
- [ ] Code follows PEP 8
- [ ] No Home Assistant imports in domain layer
- [ ] All interfaces properly implemented

---

## Next Steps

1. **During Implementation:**
   - Follow code snippets in section "Code Snippets for Copy-Paste"
   - Run tests frequently: `poetry run pytest tests/ -v`
   - Keep logging as per copilot-instructions.md

2. **After Implementation:**
   - Manual testing in HA (see TESTING_MANUAL.md)
   - Screenshot evidence of sensor working correctly
   - Performance testing with large cycle counts

3. **Before Release:**
   - QA verification of all 4 scenarios
   - Backward compatibility check
   - Documentation review

---

## References

- **Architecture Design:** ARCHITECTURE_CONTEXTUAL_LHS.md
- **Copilot Standards:** .github/copilot-instructions.md
- **Related Code:** See ARCHITECTURE_CONTEXTUAL_LHS.md Appendix
- **Domain Logic:** `domain/services/lhs_calculation_service.py`
