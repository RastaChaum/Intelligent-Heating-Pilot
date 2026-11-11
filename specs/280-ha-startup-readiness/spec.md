---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: IHP Waits for Home Assistant to Start

**Feature Branch**: `fix/issue-280`
**Created**: 2026-11-07
**Status**: Draft, written alongside the implementation
**Input**: GitHub issue #280 — "[BUG] IHP tries to read vtherm state before it is ready"

## Context

Every Home Assistant restart logs warnings for each IHP device, although nothing is wrong. They
come from two separate causes.

**IHP can load before Versatile Thermostat.** The manifest declares no dependency, so the VTherm
entity may not exist yet when IHP sets up. `HeatingCycleLifecycleManagerFactory` then cannot detect
its entity type, and `HAEnvironmentReader` resolves the device name once, in its constructor, so its
later logs show the entity id instead of the friendly name.

**IHP calculates before Home Assistant has started.** `async_setup_entry` already defers the first
update until `EVENT_HOMEASSISTANT_STARTED`, but other paths are not covered:

- `HAEventBridge` treats a tracked entity with no previous state as a meaningful change, so every
  scheduler or weather entity appearing during startup triggers a calculation.
- The delayed update is timed from setup, so a slow startup can outlast it.

A VTherm entity can also exist before it has read its sensors, so declaring the dependency alone
does not remove the room temperature warnings.

### What the logs show (one restart, about ten devices)

| First seen | Occurrences | Source | Message |
|---|---|---|---|
| 10:44:38 | 8 | `heating_cycle_lifecycle_manager_factory.py:193` | `Could not detect entity type for climate.…: Entity … not found` |
| 10:44:42 | 14 | `environment_reader.py:75` | `[climate.…] VTherm entity not found` |
| 10:44:48 | 28 | `environment_reader.py:82` | `[climate.…] No room temperature available` |
| 10:44:48 | 15 | `prediction_service.py:75` | `Cannot calculate prediction: current_temp is None` |

These warnings do not change heating decisions: with no temperature,
`ScheduleAnticipationActionUseCase` keeps the current preheating state.

## Clarifications

### Session 2026-11-07

- Q: Wait for the VTherm to report a room temperature, or for Home Assistant to have started? →
  A: For Home Assistant to have started (maintainer decision). A per-device gate on the room
  temperature was built first and replaced: it needed a new class, a timeout for a thermostat that
  never reports, and a justification for holding a waiting policy in infrastructure. Checking
  `CoreState` removes all three, at the cost described under Edge Cases.
- Q: `hass.is_running` or `CoreState.running`? → A: `CoreState.running`. `is_running` is also true
  while Home Assistant is `starting`, before `EVENT_HOMEASSISTANT_STARTED` fires.
- Q: A hard dependency or `after_dependencies`? → A: A hard dependency. IHP only works with VTherm
  entities (`docs/users/INSTALLATION.md`), and the config flow only offers them.
- Q: Should the warnings be removed from `HAEnvironmentReader` and `PredictionService`? → A: No.
  After startup, a missing temperature is a real problem that users should see.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A restart does not log false warnings (Priority: P1)

A user restarts Home Assistant. Entities appear one by one, and thermostats have not read their
sensors yet.

**Why this priority**: This is the defect of #280. The warnings look like faults and hide real ones.

**Independent Test**: With Home Assistant starting, make tracked entities appear and change, and
check that no anticipation is calculated.

**Acceptance Scenarios**:

1. **Given** Home Assistant is starting, **When** a scheduler entity appears, **Then** no
   anticipation is calculated.
2. **Given** Home Assistant is starting and the thermostat exists without a room temperature,
   **When** the thermostat reports a room temperature, **Then** no anticipation is calculated.

### User Story 2 — The sensors still receive the first calculation (Priority: P1)

**Why this priority**: Recalculations requested during startup are dropped, so without a first
publication the sensors would stay empty until something else changed.

**Independent Test**: Let Home Assistant start, run the startup update, and check that one
anticipation is calculated and published.

**Acceptance Scenarios**:

1. **Given** Home Assistant is starting and a scheduler entity appeared, **When** Home Assistant has
   started and the startup update runs, **Then** one anticipation is calculated and the sensors are
   updated.
2. **Given** Home Assistant has started and the thermostat exists without a room temperature,
   **When** the thermostat reports a room temperature, **Then** one anticipation is calculated.

### Edge Cases

- **Thermostat still without a temperature once Home Assistant has started** (a slow battery or
  Zigbee sensor): the regular warnings are logged until its first reading, which triggers a
  recalculation. This is accepted: see Clarifications.
- **Sensor that never reports**: nothing waits for it. The regular warnings are logged.
- **Entry added or reloaded while Home Assistant runs**: the startup work is scheduled straight away.
- **Entry set up while Home Assistant is `starting`**: the startup work waits for the started event.
  Scheduling it straight away would let the staggered update fire early and be dropped with no retry.
- **Entry unloaded before Home Assistant has started**: the wait is cancelled and no work is
  scheduled for the unloaded entry.
- **Versatile Thermostat not installed**: Home Assistant refuses to load IHP and logs
  `Unable to set up dependencies of 'intelligent_heating_pilot'`.
- **`calculate_anticipated_start_time` called during startup**: the service is not deferred, because
  a user asked for the result, so it can still log these warnings.
- **Thermostat `unavailable` while IHP loads**: entity type detection can still log
  `Could not detect entity type`, with a "no attribute mapper found" reason. The result is only used
  for a diagnostic log. To be confirmed on a real restart (SC-003).

## Requirements *(mandatory)*

- **FR-001**: The manifest declares `versatile_thermostat` in `dependencies`.
- **FR-002**: `HAEventBridge` calculates nothing while `hass.state` is not `CoreState.running`.
- **FR-003**: `HeatingApplication.async_update` calculates nothing while `hass.state` is not
  `CoreState.running`.
- **FR-004**: The staggered startup update publishes its result through the event bridge, because
  `async_update` does not fire the event the sensors refresh on.
- **FR-005**: `async_setup_entry` schedules the startup work with `async_at_started`, and cancels the
  wait when the entry unloads.
- **FR-006**: The domain is not changed. Waiting for startup concerns the Home Assistant lifecycle
  only, so it stays in the integration and infrastructure layers.

## Out of Scope

- Reducing the warnings repeated while a sensor is out after startup.
- Deferring the `calculate_anticipated_start_time` service during startup.
- Holding `_learning_lock` during event-driven recalculations, which already run without it.

## Success Criteria

- **SC-001**: The BDD scenarios of `tests/features/ha_startup.feature` fail when the check of FR-002
  is removed.
- **SC-002**: The full test suite, Ruff and mypy pass.
- **SC-003**: After a real Home Assistant restart, none of the four messages in the table above is
  logged, except for a thermostat still without a temperature once Home Assistant has started.
  **Not yet verified.**
