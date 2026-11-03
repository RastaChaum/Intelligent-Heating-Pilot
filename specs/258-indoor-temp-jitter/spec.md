---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Indoor Temperature Jitter Does Not Delay the Preheat

**Feature Branch**: `fix/issue-258-indoor-temp-jitter`
**Created**: 2026-11-03
**Status**: Draft
**Input**: GitHub issue #258 — "Indoor temperature jitter postpones the pending preheat timer"

## Context

Before a preheat starts, every recalculation reschedules the anticipation timer. The 15 minute
recalculation tolerance (`DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES`) only protects an
**active** preheat.

IHP reads the room temperature from the VTherm `current_temperature` attribute
(`HAEnvironmentReader`), and the event bridge triggers a recalculation whenever that attribute
changes (`HAEventBridge._handle_vtherm_change`). `current_temperature` is the raw sensor reading.
A sensor toggling between two adjacent values (0.21 °C steps) moves the pending start back and forth
by about 13 minutes at a heating slope of 0.87 °C/h. A higher reading just before the timer fires
pushes it later, and the preheat starts late.

Versatile Thermostat also publishes `ema_temp`, an exponential moving average of the same sensor.
It is the temperature VTherm regulates on, and it does not toggle with the sensor's last digit.

### What the history shows (2026-11-01, IHP v0.7.1-rc1)

| Time | `current_temperature` (°C) | Anticipated start |
|---|---|---|
| 05:10–05:16 | 19.12 ↔ 19.33 (4 toggles) | 06:24 ↔ 06:37 |
| 06:00 | 18.90 | 06:11 (timer set to 06:10:52) |
| 06:05 | 19.11 | 06:24 (timer moved to 06:23:52) |
| 06:20 | 18.90 (`ema_temp` 19.0) | 06:11 → already past → immediate trigger |

The preheat started at 06:20 instead of 06:11: 9 minutes lost.

## Clarifications

### Session 2026-11-03

- Q: Keep the earliest anticipated start for a slot, or smooth the input? → A: Smooth the input.
  IHP reads the VTherm `ema_temp` instead of `current_temperature` (maintainer decision on #258).
  The anticipated start then follows the room's trend instead of the sensor's last digit, and no new
  rule is needed on the timer.
- Q: Where is `ema_temp` published? → A: Versatile Thermostat 8 publishes it both at the root of the
  attributes and under `specific_states`; earlier versions at the root. `get_vtherm_attribute`
  already reads both.
- Q: What if the thermostat has no `ema_temp` (generic climate entity, VTherm not yet initialized)?
  → A: IHP falls back to `current_temperature`, as today. An `ema_temp` that is not a number also
  falls back.
- Q: What triggers a recalculation? → A: A change of the same temperature the calculation reads.
  A raw reading that changes while `ema_temp` stays put no longer triggers one; a change of
  `ema_temp` does, even when the raw reading is unchanged.
- Q: Does the learning (heating cycles, dead time, slope) switch to `ema_temp`? → A: No. Cycles are
  extracted from the Recorder history, where the raw reading is the measured value; learning is out
  of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The preheat start follows the smoothed room temperature (Priority: P1)

A room sensor reports 18.90 °C, then 19.11 °C, then 18.90 °C again, while the room does not really
change. Versatile Thermostat's smoothed temperature stays at 19.0 °C.

**Why this priority**: This is the defect of #258: the raw reading moves the timer later just
before it fires.

**Independent Test**: Give the thermostat a raw reading and a different smoothed temperature, read
the environment, and check that the room temperature is the smoothed one.

**Acceptance Scenarios**:

1. **Given** a thermostat reading 18.90 °C with a smoothed temperature of 19.00 °C, **When** IHP
   reads the current environment, **Then** the room temperature is 19.00 °C.
2. **Given** a thermostat reading 19.10 °C with no smoothed temperature, **When** IHP reads the
   current environment, **Then** the room temperature is 19.10 °C.

### User Story 2 — A toggling sensor no longer reschedules the preheat (Priority: P1)

**Why this priority**: Without a recalculation, the pending timer is not moved.

**Acceptance Scenarios**:

1. **Given** IHP monitors the thermostat, **When** the raw reading toggles 19.12, 19.33, 19.12,
   19.33 °C while the smoothed temperature stays 19.20 °C, **Then** no step triggers a
   recalculation.
2. **Given** IHP monitors the thermostat, **When** the smoothed temperature goes from 19.20 °C to
   19.25 °C while the raw reading stays 19.33 °C, **Then** the step triggers a recalculation.

### Edge Cases

- `ema_temp` missing (generic climate entity, older VTherm): `current_temperature` is used, for the
  calculation and for the trigger.
- `ema_temp` present but not a number: `current_temperature` is used.
- Both missing or not numbers: the environment is unavailable, as today.
- The old state has `ema_temp` and the new one not (or the reverse): the trigger compares the room
  temperature each state yields; a different value triggers a recalculation.

## Requirements *(mandatory)*

- **FR-001**: The room temperature of a thermostat is its `ema_temp`, or its `current_temperature`
  when `ema_temp` is missing or not a number.
- **FR-002**: `HAEnvironmentReader` puts that room temperature in `EnvironmentState.indoor_temperature`.
- **FR-003**: `HAEventBridge` triggers a recalculation on a thermostat state change only when that
  room temperature changes.
- **FR-004**: The rule of FR-001 lives in one infrastructure function
  (`get_vtherm_room_temperature` in `vtherm_compat.py`), used by both adapters. The domain is not
  changed: it still receives an `EnvironmentState`.

## Out of Scope

- A tolerance on the pending timer ("keep the earliest start unless later by more than the
  tolerance"): not needed once the input is smoothed.
- Heating cycle extraction and learning from the Recorder history (raw reading).
- The heating check of `IClimateDataReader` (`current_temperature < target_temperature`).

## Success Criteria

- **SC-001**: The BDD scenarios fail on the code before the fix: the environment carries the raw
  reading, and a toggling raw reading triggers recalculations.
- **SC-002**: The existing environment reader and event bridge tests still pass (fallback to
  `current_temperature`).
