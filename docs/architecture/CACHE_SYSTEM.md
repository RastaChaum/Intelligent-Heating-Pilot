# Cache System Architecture - Intelligent Heating Pilot

## Executive Summary

The Intelligent Heating Pilot (IHP) employs a **4-tier cache architecture** to optimize performance and minimize computational overhead. This document describes the cache layers, population strategies, invalidation mechanisms, and cascade update flows.

---

## 1. Cache Architecture Layers

The IHP cache system is organized into 4 distinct layers, each with specific responsibilities and lifetimes:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TIER 1: IN-MEMORY CACHE                          │
│                     (HeatingCycleLifecycleManager)                      │
├─────────────────────────────────────────────────────────────────────────┤
│  _cached_cycles_for_target_time: dict[(device_id, date), cycles]       │
│  • Lifetime: Until retention change or manual invalidation              │
│  • Purpose: Fast repeated queries for same device/date                  │
│  • Eviction: LRU with MAX_MEMORY_CACHE_ENTRIES (50) limit               │
│  • Population: On-demand via get_cycles_for_target_time()               │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     TIER 2: STORAGE CYCLE CACHE                         │
│                      (IHeatingCycleStorage)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Persistent incremental cycle storage                                   │
│  • Lifetime: Retention window (e.g., 30 days)                           │
│  • Purpose: Avoid re-extraction from HA Recorder                        │
│  • Eviction: Prune cycles older than retention (on_24h_timer)           │
│  • Population: Via update_cycles_for_window() on startup/refresh        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                   TIER 3: IN-MEMORY LHS CACHE                           │
│                      (LhsLifecycleManager)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  _cached_global_lhs: float | None                                       │
│  _cached_contextual_lhs: dict[hour, float]                              │
│  • Lifetime: Until explicit invalidation or cascade update              │
│  • Purpose: Fast access to LHS values during anticipation calculations  │
│  • Eviction: Explicit invalidation on updates                           │
│  • Population: On-demand via get_global_lhs() / get_contextual_lhs()    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    TIER 4: MODEL LHS STORAGE                            │
│                          (ILhsStorage)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Persistent storage for LHS values with timestamps                      │
│  • Lifetime: Permanent (until explicitly deleted)                       │
│  • Purpose: Persist learned heating rates across restarts               │
│  • Eviction: Manual deletion only                                       │
│  • Population: Via update_*_lhs_from_cycles() on cascade events         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cascade Update Flow

When heating cycles change (startup, retention change, 24h refresh), updates cascade through the system:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRIGGER EVENT                                        │
│         (startup / retention_change / 24h_timer)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│              HeatingCycleLifecycleManager                               │
│  1. Extract cycles from historical data                                 │
│  2. Persist to IHeatingCycleStorage (Tier 2)                            │
│  3. Call _trigger_lhs_cascade(cycles)                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│         _trigger_lhs_cascade(cycles) - ERROR ISOLATION                  │
│  ┌────────────────────────────────────────────────────────────┐         │
│  │  TRY:                                                      │         │
│  │    await update_global_lhs_from_cycles(cycles)             │         │
│  │  EXCEPT:                                                   │         │
│  │    Log error, continue (isolation)                         │         │
│  └────────────────────────────────────────────────────────────┘         │
│                           ↓                                             │
│  ┌────────────────────────────────────────────────────────────┐         │
│  │  TRY:                                                      │         │
│  │    await update_contextual_lhs_from_cycles(cycles)         │         │
│  │  EXCEPT:                                                   │         │
│  │    Log error, continue (isolation)                         │         │
│  └────────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                 LhsLifecycleManager                                     │
│  update_global_lhs_from_cycles(cycles):                                 │
│    1. Compute global LHS from cycles                                    │
│    2. Persist to ILhsStorage (Tier 4)                                   │
│    3. Update _cached_global_lhs (Tier 3)                                │
│                                                                          │
│  update_contextual_lhs_from_cycles(cycles):                             │
│    1. Compute contextual LHS by hour from cycles                        │
│    2. Persist each hour to ILhsStorage (Tier 4)                         │
│    3. Update _cached_contextual_lhs (Tier 3)                            │
└─────────────────────────────────────────────────────────────────────────┘
```

**Error Isolation Benefits:**
- Global LHS failure does not block contextual LHS update
- Contextual LHS failure does not crash the entire cascade
- Partial updates are better than complete failure

---

## 3. Contextual LHS Cache Population

Contextual LHS is populated on-demand per hour to minimize memory usage:

```
┌─────────────────────────────────────────────────────────────────────────┐
│          Application requests contextual LHS for hour X                 │
│                 get_contextual_lhs(target_time)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  Check: hour X in _cached_contextual_lhs? (Tier 3 memory)               │
│    YES → Return immediately (fast path)                                 │
│    NO  → Continue to next tier                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  Check: ILhsStorage has hour X? (Tier 4 storage)                        │
│    YES → Load value, cache in memory (Tier 3), return                   │
│    NO  → Continue to computation                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  Compute contextual LHS from provided cycles                            │
│    1. Calculate contextual_lhs_by_hour[X]                               │
│    2. If None → Fallback to global LHS                                  │
│    3. Cache in memory (Tier 3)                                          │
│    4. Return value                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Lazy Population Strategy:**
- Contextual LHS for hour X is only loaded when requested
- Reduces memory footprint (max 24 hours vs all hours eagerly)
- Storage lookup amortized across multiple anticipation calculations

**New Method: `ensure_contextual_lhs_populated()`**
- Explicit cache population for specific hour
- Supports `force_recalculate` flag for refresh
- Used when anticipation calculation detects missing hour data

---

## 4. Cache Invalidation Strategies

### 4.1 Invalidation Events

| Event                | Tier 1 (Cycles Memory) | Tier 2 (Cycle Storage) | Tier 3 (LHS Memory) | Tier 4 (LHS Storage) |
|----------------------|------------------------|------------------------|---------------------|----------------------|
| **Retention Change** | ❌ Keep valid          | ✅ Prune old cycles    | ✅ Clear all        | ✅ Recalculate       |
| **24h Timer**        | ❌ Keep valid          | ✅ Prune old cycles    | ✅ Clear all        | ✅ Recalculate       |
| **Startup**          | ❌ Empty (cold start)  | ❌ Load from storage   | ❌ Load lazily      | ❌ Read existing     |
| **Manual Eviction**  | ✅ LRU > 50 entries    | N/A                    | N/A                 | N/A                  |

### 4.2 Memory Cache Eviction (Tier 1)

To prevent unbounded memory growth, Tier 1 cache implements **LRU eviction**:

```python
MAX_MEMORY_CACHE_ENTRIES = 50

async def _evict_old_memory_cache_entries(self) -> None:
    """Evict oldest entries if cache exceeds limit."""
    if len(self._cached_cycles_for_target_time) > MAX_MEMORY_CACHE_ENTRIES:
        # Sort by date (oldest first) and remove oldest half
        sorted_keys = sorted(
            self._cached_cycles_for_target_time.keys(),
            key=lambda k: k[1]  # key[1] is the date
        )
        keys_to_remove = sorted_keys[:MAX_MEMORY_CACHE_ENTRIES // 2]

        for key in keys_to_remove:
            del self._cached_cycles_for_target_time[key]

        _LOGGER.debug("Evicted %d old memory cache entries", len(keys_to_remove))
```

**Eviction Trigger:**
- Called after `_cached_cycles_for_target_time` insertion in `get_cycles_for_target_time()`
- Removes oldest 50% of entries when limit exceeded
- Ensures memory usage stays bounded even for long-running IHP instances

---

## 5. Cache Read/Write Patterns

### 5.1 Read Operations (Tier 1 → Tier 4)

```python
# Example: Get cycles for a target time
cycles = await get_cycles_for_target_time(device_id, target_time)

# Cache lookup order:
# 1. Tier 1: Check _cached_cycles_for_target_time[(device_id, date)]
# 2. Tier 2: If miss, read from IHeatingCycleStorage.get_cache_data()
# 3. If miss, extract from historical data (HA Recorder)
# 4. Cache result in Tier 1 for next query
```

### 5.2 Write Operations (Tier 4 ← Tier 1)

```python
# Example: Update cycles for window (startup/refresh)
cycles = await update_cycles_for_window(device_id, start_time, end_time)

# Cache write order:
# 1. Extract cycles from historical data
# 2. Tier 2: Persist to IHeatingCycleStorage.append_cycles()
# 3. Cascade: Call _trigger_lhs_cascade(cycles)
# 4. Tier 4: Persist LHS to ILhsStorage.set_cached_*_lhs()
# 5. Tier 3: Update _cached_global_lhs and _cached_contextual_lhs
# 6. Tier 1: Populated on-demand by get_cycles_for_target_time()
```

---

## 6. Architecture Recommendations

### 6.1 Current Strengths ✅

1. **Layered separation**: Clear boundaries between memory and persistent caches
2. **Cascade pattern**: Automatic propagation of cycle updates to LHS
3. **Lazy loading**: Contextual LHS loaded on-demand per hour
4. **Error isolation**: `_trigger_lhs_cascade()` prevents cascade failures

### 6.2 Future Improvements 🔄

1. **TTL-based eviction**: Add time-to-live for Tier 1 entries (currently date-based only)
2. **Probabilistic eviction**: Use LRU or LFU algorithms instead of simple date-based sorting
3. **Cache metrics**: Track hit/miss rates for Tier 1 and Tier 3
4. **Partial invalidation**: Invalidate only affected hours in contextual LHS (not full clear)
5. **Async background refresh**: Pre-populate Tier 3 cache during idle periods

### 6.3 Performance Characteristics

| Operation                          | Tier 1 Hit | Tier 2 Hit | Tier 3 Hit | Tier 4 Hit | Cache Miss   |
|------------------------------------|------------|------------|------------|------------|--------------|
| **get_cycles_for_target_time()**   | ~1ms       | ~50ms      | N/A        | N/A        | ~500ms       |
| **get_global_lhs()**               | N/A        | N/A        | ~1ms       | ~20ms      | ~200ms       |
| **get_contextual_lhs(hour)**       | N/A        | N/A        | ~1ms       | ~20ms      | ~200ms       |

*(Approximate values based on typical hardware and retention periods)*

---

## 7. Testing Strategy

### 7.1 Unit Tests (Required)

- **Tier 1 eviction**: Test LRU behavior with > 50 entries
- **Cascade isolation**: Test error handling in `_trigger_lhs_cascade()`
- **Lazy population**: Test `ensure_contextual_lhs_populated()` with force_recalculate
- **Invalidation**: Test cache clearing on retention change

### 7.2 Integration Tests (Recommended)

- **End-to-end flow**: Startup → 24h timer → retention change
- **Multi-device**: Verify cache isolation between different device_ids
- **HA restart**: Verify Tier 4 (persistent) survives restart, Tier 1/3 repopulate

### 7.3 Performance Tests (Optional)

- **Cache hit ratio**: Measure Tier 1/3 hit rates under realistic workloads
- **Memory usage**: Monitor Tier 1 size with eviction disabled vs enabled
- **Cascade latency**: Measure time from cycle extraction to LHS update completion

---

## 8. Glossary

| Term                   | Definition                                                                 |
|------------------------|---------------------------------------------------------------------------|
| **Heating Cycle**      | A complete heating event: start time, end time, temperature rise          |
| **LHS**                | Learned Heating Slope (rate of temperature increase in °C/hour)           |
| **Global LHS**         | Average LHS across all heating cycles (time-agnostic)                     |
| **Contextual LHS**     | Hour-specific LHS (e.g., 8am vs 2pm may have different rates)             |
| **Retention Window**   | Number of historical days used for LHS calculation (e.g., 30 days)        |
| **Cascade Update**     | Automatic propagation of cycle changes to dependent LHS caches            |
| **Lazy Loading**       | Populate cache on-demand when value is requested (not eagerly)            |
| **LRU Eviction**       | Least Recently Used eviction (remove oldest entries first)                |

---

## 9. Related Documentation

- [ARCHITECTURE.md](../../ARCHITECTURE.md) - Overall IHP architecture and DDD principles
- [ARCHITECTURE_CONTEXTUAL_LHS.md](../../ARCHITECTURE_CONTEXTUAL_LHS.md) - Contextual LHS calculation details
- [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) - User-facing explanation of anticipation algorithm

---

## Revision History

| Version | Date       | Changes                                      | Author |
|---------|------------|----------------------------------------------|--------|
| 1.0     | 2026-02-13 | Initial cache system architecture document   | IHP    |

---

**Document Status:** ✅ **APPROVED** - Ready for implementation

**Review Cycle:** Quarterly (next review: May 2026)

**Maintainer:** IHP Architecture Team

