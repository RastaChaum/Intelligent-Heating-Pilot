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

### Phase 3: 🔨 IN PROGRESS - Gradual Coordinator Refactoring

**Strategy: Wrap, Don't Rewrite**

To maintain backward compatibility, we'll refactor incrementally:

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

### Phase 4: Update Sensors

Sensors should fire events using domain value objects:

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
3. 🔨 Refactor coordinator methods one by one:
   - [ ] `get_learned_heating_slope()` → use `HAModelStorage`
   - [ ] `get_next_scheduler_event()` → use `HASchedulerReader`
   - [ ] `async_calculate_anticipation()` → use `PredictionService`
   - [ ] `async_schedule_anticipation()` → use `HASchedulerCommander`
4. [ ] Update sensors to use domain events
5. [ ] Add integration tests
6. [ ] Remove deprecated `PreheatingCalculator`

## Timeline

- **Sprint 1** (Current): Create infrastructure adapters ✅
- **Sprint 2** (Next): Refactor coordinator storage methods
- **Sprint 3**: Refactor coordinator calculation methods
- **Sprint 4**: Integrate `HeatingPilot` aggregate
- **Sprint 5**: Update sensors and finalize migration
