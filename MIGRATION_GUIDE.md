# Migration Guide: Coordinator Refactoring

## Current State

The `IntelligentHeatingPilotCoordinator` class in `__init__.py` is a monolithic component that:
- Reads sensor data directly from Home Assistant
- Performs business logic calculations
- Manages storage and persistence
- Schedules heating actions
- Monitors for overshoot

This violates DDD principles by mixing infrastructure (HA) with domain logic.

## Target Architecture

The refactored architecture will:
1. **Coordinator** becomes a thin orchestration layer
2. **Domain Layer** (`HeatingPilot` + `PredictionService`) handles all business logic
3. **Adapters** translate between HA and domain

```
┌─────────────────────────────────────────────────────────┐
│  Coordinator (Infrastructure Orchestrator)              │
│  - Listens to HA events                                 │
│  - Calls domain via interfaces                          │
│  - Fires HA events for sensors                          │
└─────────────────────────────────────────────────────────┘
           │
           ├─► HASchedulerReader ──────► ISchedulerReader
           │                                    │
           ├─► HAModelStorage ────────► IModelStorage
           │                                    │
           ├─► HASchedulerCommander ──► ISchedulerCommander
           │                                    │
           └───────────────────────────────────┼─────────┐
                                               │         │
                                               ▼         ▼
                                        ┌──────────────────┐
                                        │  HeatingPilot    │
                                        │  (Domain Logic)  │
                                        └──────────────────┘
                                               │
                                               ▼
                                        ┌──────────────────┐
                                        │ PredictionService│
                                        └──────────────────┘
```

## Migration Strategy: Incremental Refactoring

### Phase 1: ✅ COMPLETED - Create Adapters
- [x] Implemented `HASchedulerReader`
- [x] Implemented `HAModelStorage`
- [x] Implemented `HASchedulerCommander`
- [x] Added comprehensive tests

### Phase 2: ✅ COMPLETED - Enhance Domain
- [x] Enhanced `PredictionService` with environmental calculations
- [x] Marked `PreheatingCalculator` as deprecated

### Phase 3: ✅ COMPLETED - Gradual Coordinator Refactoring

**Strategy: Wrap, Don't Rewrite**

Successfully refactored coordinator incrementally while maintaining backward compatibility:

#### Step 3.1: Add Adapter Instances to Coordinator
```python
class IntelligentHeatingPilotCoordinator:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        # Existing initialization...
        
        # NEW: Create adapter instances
        self._scheduler_reader = HASchedulerReader(
            hass, 
            self.get_scheduler_entities()
        )
        self._model_storage = HAModelStorage(hass, config_entry.entry_id)
        # Note: scheduler_commander needs a single entity, managed per-action
```

#### Step 3.2: Delegate Storage Operations
Replace direct `_data` access with adapter calls:

**Before:**
```python
def get_learned_heating_slope(self) -> float:
    slopes = self._data.get("historical_slopes", [])
    # ... calculation logic
    return lhs
```

**After:**
```python
async def get_learned_heating_slope(self) -> float:
    return await self._model_storage.get_learned_heating_slope()
```

#### Step 3.3: Delegate Scheduler Reading
Replace `get_next_scheduler_event()` with adapter:

**Before:**
```python
def get_next_scheduler_event(self) -> tuple[datetime | None, float | None, str | None]:
    # 70+ lines of parsing logic
    return chosen_time, chosen_temp, chosen_entity
```

**After:**
```python
async def get_next_scheduler_event(self) -> tuple[datetime | None, float | None, str | None]:
    timeslot = await self._scheduler_reader.get_next_timeslot()
    if timeslot:
        return timeslot.target_time, timeslot.target_temp, timeslot.timeslot_id
    return None, None, None
```

#### Step 3.4: Use Domain for Predictions
Replace `async_calculate_anticipation()` with domain service:

**Before:**
```python
async def async_calculate_anticipation(self, ...) -> dict | None:
    # 100+ lines of calculation and correction factors
    return result
```

**After:**
```python
async def async_calculate_anticipation(self, ...) -> dict | None:
    # Get environment state
    env_state = EnvironmentState(
        current_temp=self.get_vtherm_current_temp(),
        outdoor_temp=outdoor_temp,
        humidity=humidity,
        timestamp=dt_util.now(),
        cloud_coverage=cloud_coverage,
    )
    
    # Get next timeslot from adapter
    timeslot = await self._scheduler_reader.get_next_timeslot()
    if not timeslot:
        return None
    
    # Use domain prediction service
    lhs = await self._model_storage.get_learned_heating_slope()
    prediction_service = PredictionService()
    prediction = prediction_service.predict_heating_time(
        current_temp=env_state.current_temp,
        target_temp=timeslot.target_temp,
        learned_slope=lhs,
        target_time=timeslot.target_time,
        outdoor_temp=env_state.outdoor_temp,
        humidity=env_state.humidity,
        cloud_coverage=env_state.cloud_coverage,
    )
    
    # Convert domain result back to dict for backward compatibility
    return {
        ATTR_NEXT_SCHEDULE_TIME: timeslot.target_time,
        ATTR_NEXT_TARGET_TEMP: timeslot.target_temp,
        ATTR_ANTICIPATED_START_TIME: prediction.anticipated_start_time,
        "anticipation_minutes": prediction.estimated_duration_minutes,
        "current_temp": env_state.current_temp,
        "scheduler_entity": timeslot.timeslot_id,
        ATTR_LEARNED_HEATING_SLOPE: prediction.learned_heating_slope,
    }
```

#### Step 3.5: Use HeatingPilot for Decisions (Future)
Eventually, replace decision logic with `HeatingPilot` aggregate:

```python
async def decide_action(self) -> HeatingDecision:
    # Create adapters
    scheduler_reader = HASchedulerReader(...)
    model_storage = HAModelStorage(...)
    scheduler_commander = HASchedulerCommander(...)
    
    # Create domain aggregate
    pilot = HeatingPilot(
        scheduler_reader=scheduler_reader,
        model_storage=model_storage,
        scheduler_commander=scheduler_commander,
    )
    
    # Get environment state
    env_state = self._build_environment_state()
    
    # Let domain decide
    decision = await pilot.decide_heating_action(env_state)
    
    # Execute decision
    if decision.action == HeatingAction.START_HEATING:
        await scheduler_commander.run_action(...)
```

### Phase 4: ✅ COMPLETED - Update Sensors

Sensors updated to expose domain-calculated confidence metrics:

**Before:**
```python
# Coordinator fires raw dict
self.hass.bus.async_fire(f"{DOMAIN}_anticipation_calculated", payload)
```

**After:**
```python
# Coordinator fires structured domain data
event_data = {
    "entry_id": self.config.entry_id,
    "prediction": prediction,  # PredictionResult domain object
    "timeslot": timeslot,      # ScheduleTimeslot domain object
}
self.hass.bus.async_fire(f"{DOMAIN}_anticipation_calculated", event_data)
```

## Benefits of This Approach

1. **Backward Compatible**: Existing code continues to work
2. **Incremental**: Can be done step-by-step, testing each change
3. **Safe**: Each refactoring can be validated independently
4. **Testable**: Domain logic becomes testable without HA
5. **Maintainable**: Clear separation of concerns

## Testing Strategy

For each refactored method:

1. **Integration test**: Verify existing behavior still works
2. **Unit test**: Test new domain method in isolation
3. **Regression test**: Ensure sensors still receive correct data

## Rollback Plan

Each commit should be atomic and revertible:
- If a refactoring causes issues, revert that commit
- Keep old methods available with deprecation warnings
- Use feature flags if necessary for gradual rollout

## Next Steps

1. ✅ Create adapters (DONE)
2. ✅ Enhance domain logic (DONE)
3. ✅ Refactor coordinator methods (DONE):
   - [x] `get_learned_heating_slope()` → use `HAModelStorage`
   - [x] `get_next_scheduler_event()` → use `HASchedulerReader`
   - [x] `async_calculate_anticipation()` → use `PredictionService`
   - [ ] `async_schedule_anticipation()` → use `HASchedulerCommander` (Future)
4. ✅ Update sensors to expose domain confidence (DONE)
5. [ ] Add integration tests (Future)
6. [ ] Remove deprecated `PreheatingCalculator` (Future)
7. [ ] Remove legacy sync methods after validation period (Future)

## Timeline

- **Sprint 1**: Create infrastructure adapters ✅ DONE
- **Sprint 2**: Refactor coordinator with DDD adapters ✅ DONE
- **Sprint 3**: Update sensors with domain confidence ✅ DONE
- **Sprint 4**: Timestamped slope storage and contextual LHS ✅ DONE
- **Sprint 5** (Future): Integrate `HeatingPilot` aggregate for full domain decisions
- **Sprint 6** (Future): Remove legacy code and finalize migration

---

## Storage Format Migration: v1 → v2 (Sprint 4)

### Overview

**Issue**: The original LHS (Learning Heating Slope) included ALL positive slopes, even when heating was OFF (e.g., solar gain, appliances), contaminating the learning data.

**Solution**: 
1. Only record slopes when heating is **actually ON** (hvac_mode='heat' AND current_temp < target_temp)
2. Add **timestamps** to each slope record for contextual retrieval
3. Use **time-windowed LHS** for predictions (default: 6-hour window)

### Storage Format Changes

#### v1 Format (Legacy)
```json
{
  "historical_slopes": [2.0, 2.2, 2.1, 2.3],
  "learned_heating_slope": 2.15
}
```

#### v2 Format (New)
```json
{
  "slope_data_list": [
    {"timestamp": "2025-11-17T10:00:00+00:00", "slope_value": 2.0},
    {"timestamp": "2025-11-17T11:30:00+00:00", "slope_value": 2.2},
    {"timestamp": "2025-11-17T13:00:00+00:00", "slope_value": 2.1},
    {"timestamp": "2025-11-17T14:30:00+00:00", "slope_value": 2.3}
  ],
  "learned_heating_slope": 2.15
}
```

### Automatic Migration

The `HAModelStorage` adapter **automatically migrates** v1 data to v2 format on first load:
- Existing float slopes are converted to timestamped entries
- Timestamps are evenly distributed over the past retention period (7 days)
- Old format is preserved for backward compatibility during transition

### New Domain Value Object: `SlopeData`

```python
@dataclass(frozen=True)
class SlopeData:
    """Immutable record of a heating slope measurement."""
    slope_value: float  # °C/hour, must be positive
    timestamp: datetime  # UTC, timezone-aware required
```

**Validation**:
- Rejects negative or zero slopes (ValueError)
- Requires timezone-aware timestamps (ValueError)
- Immutable (frozen=True)

### Configuration Options

Two new optional configuration keys:

| Config Key | Default | Description |
|------------|---------|-------------|
| `lhs_window_hours` | 6.0 | Time window (hours) for contextual LHS retrieval |
| `lhs_retention_days` | 30 | How many days to retain slope data |

**Example Configuration**:
```yaml
intelligent_heating_pilot:
  vtherm_entity_id: climate.bedroom
  scheduler_entities: 
    - schedule.bedroom_heating
  lhs_window_hours: 8.0      # Use 8-hour window for predictions
  lhs_retention_days: 45     # Keep 45 days of history
```

### Contextual LHS Behavior

**Before**: Used global average of all positive slopes
```python
lhs = await model_storage.get_learned_heating_slope()  # Global average
```

**After**: Uses time-windowed average for target time
```python
# Get slopes from 6 hours before target time
lhs = await _get_contextual_lhs(target_time)

# Falls back to global LHS with WARNING if window is empty
```

**Benefits**:
- More accurate predictions (time-of-day effects)
- Accounts for solar gain variations by time
- Better handling of variable household activities

### Heating State Detection

**Enhanced Logic** in `environment_reader.is_heating_active()`:

```python
# Old: hvac_action == "heating" OR hvac_mode == "heat"
# New: hvac_mode == "heat" AND current_temp < target_temp
```

This ensures slopes are only recorded when:
1. Heating mode is enabled
2. There's actual demand (temperature below target)

### Data Retention and Cleanup

- **Automatic cleanup** on load: removes entries older than `retention_days`
- **Max history size**: 100 most recent entries (in-memory limit)
- **Storage size**: Typically ~5KB per 100 entries (negligible)

### Interface Changes (Backward Compatible)

#### New Methods (Preferred)
```python
# Save timestamped slope
await model_storage.save_slope_data(slope_data: SlopeData)

# Get all with timestamps
slopes = await model_storage.get_all_slope_data() -> list[SlopeData]

# Query time window
slopes = await model_storage.get_slopes_in_time_window(
    before_time=target_time,
    window_hours=6.0
) -> list[SlopeData]
```

#### Legacy Methods (Deprecated, Still Supported)
```python
# Old method auto-creates SlopeData with current timestamp
await model_storage.save_slope_in_history(slope: float)

# Old method returns float list
slopes = await model_storage.get_slopes_in_history() -> list[float]
```

### Testing

✅ **Unit Tests**:
- `test_slope_data.py`: 7 tests for value object validation
- `test_model_storage_timestamped.py`: 10 tests for storage adapter

✅ **Integration Tests**:
- `test_time_windowed_lhs.py`: End-to-end validation of time-windowed behavior

### Rollback Strategy

If issues occur:
1. **No data loss**: v1 format is preserved during migration
2. **Revert code**: Old methods still work with v2 storage
3. **Manual rollback**: Delete `.storage/intelligent_heating_pilot_model_*` files to reset

### Future Enhancements (Planned)

The `SlopeData` value object is designed for future ML features:
```python
@dataclass(frozen=True)
class SlopeData:
    slope_value: float
    timestamp: datetime
    # Future fields for ML:
    # outdoor_temp: float | None
    # humidity: float | None
    # time_of_day: int | None
    # day_of_week: int | None
```

This will enable:
- Weather-aware predictions
- Time-of-day pattern recognition
- Weekly schedule optimization
