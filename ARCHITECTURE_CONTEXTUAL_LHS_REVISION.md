# Contextual LHS Architecture - REVISION SUMMARY

**Date:** 2026-02-09
**Status:** Ready for QA Phase
**Phase:** Phase 1b Complete - Architecture Updated per User Feedback

---

## Critical Changes from Initial Design

### 1. **Cycle Storage & LHS Association** ✅

**BEFORE:**
```python
cycle = HeatingCycle(start_time, end_time, ...)  # NO LHS
# LHS calculated separately, when?
```

**AFTER:**
```python
cycle = HeatingCycle(start_time, end_time, lhs_value=15.2)  # LHS IN cycle
# Each cycle OWNS its LHS value
```

**Impact:**
- `HeatingCycle` domain object must include `lhs: float` field
- Cycles extracted from history already have LHS calculated (via `HeatingCycleService`)
- No separate calculation pass needed

---

### 2. **Contextual Cache Structure** ✅

**BEFORE:**
```python
cache[hour] = 14.75  # Just the value
```

**AFTER:**
```python
cache[hour] = {
    "lhs": 14.75,
    "cycle_count": 3,  # NEW: How many cycles contributed
    "updated_at": "2026-02-09T20:53:03.450922+00:00"
}
```

**Impact:**
- HAModelStorage must store richer metadata (cycle_count)
- Sensor can display: "14.75°C/h (from 3 cycles)"
- Cache entry type: `ContextualLHSCacheEntry` (new value object)

---

### 3. **Recalculation Frequency** ✅

**BEFORE (Initial Design):**
- Every 24 hours via timer only
- ❌ Misses cycles added at startup/retention change

**AFTER (User Feedback):**
- **EVERY TIME cycles are added/modified**:
  - ✅ Startup (initial extraction)
  - ✅ Redémarrage (reload)
  - ✅ Retention parameter change
  - ✅ New cycles detected (24h periodic check)

**Impact:**
- Recalculation is NOT done in a separate timer phase
- Both calculators (Global + Contextual) triggered IMMEDIATELY after cycle extraction
- `ExtractHeatingCyclesUseCase.execute()` MUST call both services before returning

**Sequence:**
```
ExtractHeatingCyclesUseCase.execute()
  ├─ Extract cycles from history
  ├─ Calculate each cycle's LHS (if not present)
  ├─ GlobalLHSCalculatorService.calculate_global_lhs(cycles)
  │  └─ model_storage.set_cached_global_lhs(avg, now)
  ├─ ContextualLHSCalculatorService.calculate_contextual_lhs(cycles)
  │  └─ for hour in 0..23:
  │     └─ model_storage.set_cached_contextual_lhs(hour, lhs, count, now)
  └─ Return cycles + results
```

---

### 4. **LHS Calculator Services** ✅

**BEFORE (Initial Design):**
```python
class LHSCalculationService:
    def calculate_global_lhs(cycles) -> float
    def calculate_contextual_lhs(cycles) -> dict  # AMBIGUOUS
```

**AFTER (User Feedback - REFACTOR):**

**DELETE:**
```python
LHSCalculationService  # REMOVED
```

**CREATE TWO SPECIALIZED SERVICES:**

#### A. `GlobalLHSCalculatorService`
```python
class GlobalLHSCalculatorService:
    """Calculate single global LHS from all cycles."""

    def calculate_global_lhs(self, cycles: list[HeatingCycle]) -> float:
        """Average LHS of ALL cycles.

        Returns:
            float: Average heating slope (°C/h) or DEFAULT if no cycles
        """
        # Implementation: sum(cycle.lhs for cycle in cycles) / len(cycles)
```

#### B. `ContextualLHSCalculatorService`
```python
class ContextualLHSCalculatorService:
    """Calculate per-hour contextual LHS from all cycles."""

    def calculate_contextual_lhs(
        self,
        cycles: list[HeatingCycle]
    ) -> dict[int, ContextualLHSData]:
        """Group cycles by start_hour and calculate hour-by-hour average LHS.

        Returns:
            dict: {0: ContextualLHSData(...), 1: ContextualLHSData(...), ..., 23: ...}
        """
        # Implementation:
        # 1. Group cycles by cycle.start_time.hour
        # 2. For each hour: calculate avg(lhs) and count
        # 3. Return dict with all 24 hours (None for empty hours)
```

**Impact:**
- Clear separation of concerns
- Single responsibility per service
- Easier to test independently
- Type hints unambiguous

---

### 5. **Open Questions - RESOLVED** ✅

User provided explicit answers:

| Question | Initial Options | **User Decision** |
|----------|------------------|-------------------|
| Cache Invalidation | A (24h only), B (on config change), C (staleness check) | **B** - Recalc on every cycle addition (invalidates old approach) |
| Sync vs Async | Async methods vs Sync only | **Synchronous** - Pre-loaded cache, sensors need sync access |
| Cycles spanning days | Start hour vs Active hours | **Start hour** - Accepted as-is ✓ |
| Storage volume | Cleanup strategy for 24x cache | **24x** - One entry per hour, minimal footprint |
| next_schedule_time refresh | On startup only vs event-driven | **On startup + on scheduler change** - Event-driven refresh |

**Impact:** These decisions remove ambiguity and guide implementation

---

## Architecture Summary (FINAL)

### Data Flow (REVISED)

```
┌──────────────────────────────────────────────────────┐
│  Coordinator.async_load() OR retention_change()      │
└────────────────┬─────────────────────────────────────┘
                 │
                 ↓
┌──────────────────────────────────────────────────────┐
│  ExtractHeatingCyclesUseCase.execute(start, end)     │
│  - Fetch from Home Assistant recorder                │
│  - HeatingCycleService extracts cycles               │
│  - Each cycle HAS lhs_value                          │
└────────────────┬─────────────────────────────────────┘
                 │
        ┌────────┴────────┬──────────────────┐
        │                 │                  │
        ↓                 ↓                  ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Global LHS   │ │ Contextual   │ │ Cache        │
│ Calculator   │ │ LHS          │ │ Persistence  │
│              │ │ Calculator   │ │              │
│ avg(all)     │ │ group by     │ │ Store in     │
│              │ │ hour         │ │ HAModelStore │
└────────┬─────┘ └──────┬───────┘ └──────────────┘
         │              │
         └──────┬───────┘
                ↓
        ┌──────────────────────┐
        │ Coordinator cache    │
        │ - _lhs_cache         │
        │ - _contextual_cache  │ (per hour)
        └──────────┬───────────┘
                   │
        ┌──────────┴───────────┐
        │                      │
        ↓                      ↓
┌───────────────────┐ ┌────────────────────┐
│ Global LHS Sensor │ │ Contextual LHS     │
│                   │ │ Sensor             │
│ native_value:     │ │                    │
│ 14.75°C/h         │ │ native_value:      │
│                   │ │ 14.75°C/h or       │
│                   │ │ "unknown"          │
└───────────────────┘ └────────────────────┘
```

### Service Interactions

```
GlobalLHSCalculatorService:
├─ Input: list[HeatingCycle] (cycles have .lhs)
├─ Logic: avg(cycle.lhs for all cycles)
└─ Output: float (global average)

ContextualLHSCalculatorService:
├─ Input: list[HeatingCycle] (cycles have .lhs + .start_time)
├─ Logic:
│  ├─ Group by cycle.start_time.hour (0-23)
│  ├─ For each hour:
│  │  ├─ cycles_for_hour = [c for c in cycles if c.start_time.hour == hour]
│  │  ├─ avg_lhs = avg(c.lhs for c in cycles_for_hour) or None
│  │  ├─ count = len(cycles_for_hour)
│  │  └─ Create ContextualLHSData(lhs, count, updated_at)
│  └─ Return dict[hour] = ContextualLHSData
└─ Output: dict[int, ContextualLHSData | None]
```

---

## Implementation Checklist

### Phase 2: QA (Write Tests)
- [ ] Tests for `GlobalLHSCalculatorService.calculate_global_lhs()`
- [ ] Tests for `ContextualLHSCalculatorService.calculate_contextual_lhs()`
- [ ] Tests for edge cases (no cycles, single cycle, many cycles)
- [ ] Tests for `ContextualLHSData` value object
- [ ] End-to-end integration tests (all 4 scenarios)

### Phase 3: Developer (Implement)
- [ ] Create `GlobalLHSCalculatorService` (domain/services/)
- [ ] Create `ContextualLHSCalculatorService` (domain/services/)
- [ ] Create `ContextualLHSData` value object (domain/value_objects/)
- [ ] Update `HeatingCycle` to include `lhs: float`
- [ ] Update `ExtractHeatingCyclesUseCase` to call both calculators
- [ ] Update `HAModelStorage` to persist `ContextualLHSCacheEntry`
- [ ] Update `IModelStorage` interface with new methods
- [ ] Update `Coordinator` to track next_schedule_time + contextual cache
- [ ] Update sensors to use new methods
- [ ] Remove old `LHSCalculationService`

### Phase 4: Tech Lead (Review)
- [ ] Verify DDD compliance (domain layer clean)
- [ ] Verify test coverage (>80%)
- [ ] Verify all linters pass (ruff, mypy, bandit)
- [ ] Verify integration tests pass (all 4 scenarios)
- [ ] Code review for quality
- [ ] Merge to main

---

## Next Steps

✅ **Phase 1b Complete:** Architecture revised and documented
🔲 **Phase 2 Ready:** QA Engineer to write RED tests
🔲 **Phase 3 Ready:** Developer to implement
🔲 **Phase 4 Ready:** Tech Lead to review & merge
🔲 **Phase 5 Ready:** User validation in HA UI
