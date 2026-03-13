# Codebase Audit Report — Intelligent Heating Pilot

**Date:** 2026-03-07
**Branch:** integration
**Version:** 0.5.0-rc.1
**Scope:** Full codebase audit — architecture, HA integration, resource management, tests, code quality

---

## Context

This audit was triggered by a systematic Home Assistant watchdog reboot occurring in production after
3–4 minutes when 10 IHP devices are configured. The issue does not reproduce with a single device in
test environments. The goal of this report is to identify root causes and areas for improvement,
without prescribing detailed solutions.

---

## 1. Critical Issues — Probable Causes of HA Reboot

These issues have a direct scaling effect: harmless with 1 device, compounding with 10.

### 1.1 Untracked Timer Subscriptions — `__init__.py` lines 152–202

`async_track_point_in_time()` is called **3 times per device** during `async_setup_entry()`:
- line 152: startup update timer
- line 157: startup extraction timer
- line 198: late update timer

The return value (unsubscribe callback) is **never stored** and **never registered with
`entry.async_on_unload()`**. With 10 devices, 30 orphaned subscriptions accumulate in the HA event
loop and are never cleaned up, even after entry unload.

> **Recommendation:** Store each `async_track_point_in_time()` result and register it via
> `entry.async_on_unload()`.

### 1.2 Fire-and-Forget `async_create_task()` Without Error Handling — `__init__.py` lines 146, 150, 192

Three tasks per device are created with `hass.async_create_task()` inside `@callback` functions
without `.add_done_callback()`. Exceptions raised inside these tasks are silently discarded, and
there is no guarantee of resource cleanup on failure. Compare with `event_bridge.py` line 166, which
correctly attaches `_on_recalculate_task_done` as a done callback.

> **Recommendation:** Attach a logging done-callback to every `async_create_task()` call in
> `__init__.py`, following the pattern already established in `event_bridge.py`.

### 1.3 Fire-and-Forget Task in Sensor Callback — `sensor.py` line 627

`handle_dead_time_updated()` is a `@callback` function that calls
`self.hass.async_create_task(self._async_refresh_dead_time())` without a done callback. An exception
in `_async_refresh_dead_time()` is silently swallowed with 10 devices firing this event repeatedly.

> **Recommendation:** Add a done callback or wrap the call with a logged error handler.

### 1.4 No Exception Guard in Base Sensor Event Callback — `sensor.py` lines 81–92

`handle_anticipation_event()` in `IntelligentHeatingPilotSensorBase` calls
`self._handle_anticipation_result(data)` with no `try/except`. An unhandled exception propagates
directly into the HA event bus dispatcher. With 80 listeners registered across 10 devices (8 sensors
× 10), a single bad event can cascade.

> **Recommendation:** Wrap `_handle_anticipation_result()` calls in a `try/except Exception` with
> error logging.

---

## 2. High-Severity Issues

### 2.1 Service Handler Iterates All Devices on Every Call — `__init__.py` lines 238–245

`handle_calculate_anticipated_start_time()` iterates `hass.data[DOMAIN].items()` and calls
`entity_reg.async_get()` for each device to find the entry owning the requested entity. With 10
devices this is inefficient and will worsen as device count grows.

> **Recommendation:** Pre-compute and cache the entity-to-entry mapping at setup time.

### 2.2 `async_update_options()` Creates a Fire-and-Forget Task — `__init__.py` line 404

After reloading the entry, a bare `hass.async_create_task(coordinator.async_update())` is called
with no error handling. If the reload changes coordinator state unexpectedly, this task fails
silently.

> **Recommendation:** Add a done callback or use `await coordinator.async_update()` directly.

---

## 3. Architecture & Domain Layer

### 3.1 Compliance — Excellent

The domain layer contains zero `homeassistant.*` imports. All 14 interfaces are pure ABCs. All 11
value objects are `@dataclass(frozen=True)` with `__post_init__` validation. Type hints and
Google-style docstrings are present on >95% of public APIs.

### 3.2 Bare HA Import in Application Use Case — `application/use_cases/schedule_anticipation_action_use_case.py` line 12

`from homeassistant.util import dt as dt_util` is a direct, unguarded import. The two lifecycle
managers use a `try/except ImportError` pattern for the same import, which is the correct approach
for test portability.

> **Recommendation:** Wrap the import in `try/except ImportError` to match the existing pattern.

### 3.3 Duplicate Code Block in Domain Service — `domain/services/heating_cycle_service.py` ~lines 382 and 486

The `_calculate_dead_time_cycle()` call is duplicated within two methods. The second invocation
overrides the first result in the same scope.

> **Recommendation:** Remove the duplicate assignment.

### 3.4 Long Method — `domain/services/heating_cycle_service.py`

`extract_heating_cycles()` is approximately 170 lines and embeds a non-trivial state machine
inline. The method is functional but reduces readability and testability.

> **Recommendation:** Extract the state machine iteration into a private helper method.

### 3.5 Incomplete ML Strategy — `domain/services/ml_decision_strategy.py`

The ML decision strategy contains `TODO` placeholders and returns hardcoded defaults. It is not
connected to any ML backend interface.

> **Recommendation:** Complete when the ML model interface is finalized, or mark with a formal
> `NotImplementedError` to prevent accidental production use.

### 3.6 Unresolved TODOs in Sub-cycle Tariff Calculation — `domain/services/heating_cycle_service.py` ~lines 502, 521

Two `TODO` markers indicate that tariff attribution for sub-cycles is not yet computed.

> **Recommendation:** Implement tariff sub-cycle calculation or document its absence as a known
> limitation.

---

## 4. Test Coverage

### 4.1 Overall Coverage — 26.1% (1,215 / 4,655 lines)

Coverage is low relative to production risk. The domain and application layers are the best-covered;
the HA integration layer has significant gaps.

### 4.2 `config_flow.py` — Integration Test Only

The configuration flow is exercised by a single integration test but has no unit-level tests for
option validation, edge cases, or error paths.

> **Recommendation:** Add unit tests for each config/option flow step and validation branch.

### 4.3 `view.py` — Untested

The REST API view has zero test coverage.

> **Recommendation:** Add unit tests for each HTTP endpoint, including error responses.

### 4.4 `heating_application.py` — Partially Tested (Integration Only)

The main coordinator (~29 KB) is covered by integration tests only. Initialization paths, error
handling, and lifecycle transitions are not unit-tested.

> **Recommendation:** Add unit tests for the coordinator's initialization, cleanup, and options
> handling.

### 4.5 Adapter Coverage Gaps

Six infrastructure adapters have no unit tests:
- `entity_attribute_validator.py`
- `entity_attribute_mapper_registry.py`
- `generic_climate_attribute_mapper.py`
- `base_entity_attribute_mapper.py`
- `decision_strategy_factory.py`
- `utils.py`

> **Recommendation:** Add unit tests for each adapter, focusing on translation logic and edge cases.

---

## 5. General Quality

### 5.1 Strengths

| Area | Status |
|---|---|
| Domain purity (no HA imports in domain/) | Excellent |
| Interfaces (14 ABCs) | Excellent |
| Value objects (11 frozen dataclasses with validation) | Excellent |
| Type hint coverage | >95% |
| Docstring coverage | >95% |
| Logging convention (DEBUG/INFO/WARNING) | Compliant |
| Constants centralization (`domain/constants.py`) | Compliant |
| Dependency management (Poetry, no conflicts) | Healthy |
| BDD scenarios (59 across 9 feature files) | Well-designed |
| Fixture centralization (`tests/unit/domain/fixtures.py`) | Good |
| Code duplication | None detected |

### 5.2 RecorderQueue — No Timeout on Extraction

The recorder queue serializes all device extractions but has no timeout mechanism. A stalled
recorder query would block subsequent devices indefinitely; at 10 devices the HA watchdog could
trigger before all extractions complete.

> **Recommendation:** Add a configurable timeout to recorder queue acquisition and log a warning if
> exceeded.

### 5.3 `_LOGGER` Private Access in Service Handler — `__init__.py` lines 260, 267

`handle_calculate_anticipated_start_time()` accesses `coordinator._vtherm_id` and
`coordinator._orchestrator` via private attributes, bypassing the coordinator's public API.

> **Recommendation:** Expose dedicated public methods on `HeatingApplication` for these lookups.

---

## 6. Priority Summary

| # | Issue | Severity | File |
|---|---|---|---|
| 1.1 | Untracked timer subscriptions | Critical | `__init__.py:152–202` |
| 1.2 | Fire-and-forget tasks without done callback | Critical | `__init__.py:146,150,192` |
| 1.3 | Fire-and-forget task in sensor callback | High | `sensor.py:627` |
| 1.4 | No exception guard in base sensor callback | High | `sensor.py:81–92` |
| 2.1 | O(n) service handler entity lookup | High | `__init__.py:238–245` |
| 2.2 | Fire-and-forget task after reload | Medium | `__init__.py:404` |
| 3.2 | Unguarded HA import in use case | Medium | `schedule_anticipation_action_use_case.py:12` |
| 3.3 | Duplicate dead_time_cycle calculation | Low | `heating_cycle_service.py:~382,486` |
| 3.4 | Overly long `extract_heating_cycles()` | Low | `heating_cycle_service.py` |
| 3.5 | Incomplete ML strategy placeholder | Low | `ml_decision_strategy.py` |
| 4.1–4.5 | Test coverage gaps (26.1%) | High | `config_flow.py`, `view.py`, adapters |
| 5.2 | No timeout on RecorderQueue | Medium | `infrastructure/recorder_queue.py` |
| 5.3 | Private attribute access in service handler | Low | `__init__.py:260,267` |

---

*Audit performed by automated multi-agent analysis. References to line numbers are approximate and
should be verified against the branch at time of reading.*
