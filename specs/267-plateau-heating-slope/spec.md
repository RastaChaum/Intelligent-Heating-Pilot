---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Plateau Below the Target Does Not Lower the Learned Heating Slope

**Feature Branch**: `fix/issue-267-plateau-slope`
**Created**: 2026-11-05
**Status**: Draft
**Input**: GitHub issue #267 — "A cycle that settles on a plateau below its target lowers the
learned slope at every preheat"

## Context

A heating cycle ends when the room is within `temp_delta_threshold` of the target, when the target
drops, or at `max_cycle_duration_minutes` (`HeatingCycleService._should_end_cycle`).
`HeatingCycle.avg_heating_slope` divides the rise from the end of the dead time to the end of the
cycle by the duration of that window.

A Versatile Thermostat driven by TPI often settles a few tenths **below** its target: proportional
regulation keeps a static error when `coef_int` is low. The room rises, then stays flat at partial
power until the comfort slot ends. The cycle never reaches the target, so it runs until the next
eco slot, and the hours spent on the plateau are counted as heating time.

Since #255 a slow cycle is no longer discarded. A plateau cycle is learned with a slope that is far
too low, the next preheat starts earlier, its plateau lasts longer, and its slope is lower again.
The loop only stops at `max_cycle_duration_minutes`.

### What the history shows (2026-11-04 and 2026-11-05, VTherm smoothed temperature)

| Room | Plateau | Slope learned today | Slope of the rise |
|---|---|---|---|
| Bathroom upstairs, 2026-11-05 | 19.6–19.76 °C from 05:07 to 07:37, target reached at 08:01 | 0.22 °C/h | 0.84 °C/h |
| Bathroom upstairs, 2026-11-04 | 19.6–19.7 °C from 05:52 to 07:30 | 0.31 °C/h | 0.83 °C/h |
| Bedroom A, 2026-11-04 | 19.3–19.5 °C from 05:04 to 08:29 | 0.17 °C/h | 0.49 °C/h |
| Living room (underfloor), 2026-11-05 | none: rises steadily until 08:45 | 0.30 °C/h | 0.30 °C/h |

The global slope of the bathroom is 1.01 °C/h. Its contextual slope for the morning slot fell from
1.09 to 0.57 °C/h in one day, and Bedroom A's from 0.37 to 0.12 °C/h, which made it start heating
six hours before its slot.

## Clarifications

### Session 2026-11-05

- Q: Where does the heating phase end? → A: At the first plateau: the first reading of the heating
  phase after which the room gains less than `PLATEAU_RISE_TOLERANCE_C` (0.1 °C, one sensor step)
  for at least `PLATEAU_MIN_DURATION_MINUTES` (60 minutes). The heating slope is measured from the
  end of the dead time to that reading. Without such a plateau, the heating phase ends with the
  cycle, as today.
- Q: Does a plateau that ends before the cycle (the room climbs again, for example with the sun)
  count? → A: Yes. Only the first plateau is looked for: what follows it does not describe how the
  heating warms the room from its start.
- Q: Does it cut a genuinely slow heating system (underfloor)? → A: A room still rising gains
  0.1 °C in less than an hour as long as it heats faster than 0.1 °C/h, so it is not cut. A slower
  room can be cut at a step, but its slope is unchanged: a steady rise measured up to any of its
  readings gives the same rate.
- Q: How far must the plateau last? → A: At least `PLATEAU_MIN_DURATION_MINUTES` before the cycle
  ends. A flat stretch shorter than that at the end of the cycle is not a plateau: the cycle keeps
  its full window.
- Q: Which cycle values change? → A: Only the heating slope. The cycle keeps its start, end, end
  temperature, dead time, disturbance status and slot: the cycle end still files it under its hour
  (#214, #254) and its dead time is unchanged.
- Q: What if the plateau starts at the end of the dead time? → A: The heating phase is then empty,
  the slope is 0 and the cycle is not learned (#255 already excludes a cycle whose room did not
  warm after its dead time).
- Q: Split cycles (`cycle_split_duration_minutes`)? → A: Sub-cycles cover the heating phase up to
  its end, so every sub-cycle gets the slope of the rise. The plateau is not split into sub-cycles.
- Q: Cycles already in the cache? → A: They keep their slope until `reset_learning` re-extracts
  them from the Recorder, as for #254, #255 and #260. A cycle cached before the end of its heating
  phase was recorded falls back to its full window.
- Q: New option? → A: No. Both thresholds are domain constants.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A preheat that settles below its target learns the slope of its rise (Priority: P1)

A room whose thermostat stabilises a few tenths below the target learns how fast it heats, not how
long it waits on its plateau.

**Why this priority**: The plateau lowers the slope at every preheat, so the room starts heating
hours too early and the loop only stops at the maximum cycle duration.

**Independent Test**: Extract a cycle that rises 1.0 °C/h after its dead time, then stays flat
0.3 °C below the target for two hours, and read its heating slope.

**Acceptance Scenarios**:

1. **Given** a cycle from 18.5 °C, flat for 30 minutes, rising 1.0 °C/h until 19.7 °C and then
   flat until it is switched off two hours later, **When** it is extracted, **Then** its heating
   slope is 1.0 °C/h.
2. **Given** that cycle, **When** it is extracted, **Then** it ends when it is switched off, with
   the end temperature of its plateau, and its dead time is unchanged.
3. **Given** a cycle that stays flat for 90 minutes, then climbs to its target, **When** it is
   extracted, **Then** its heating slope is measured up to the start of the flat stretch.

### User Story 2 — A cycle without plateau is learned as today (Priority: P1)

A room that keeps warming until its target, however slowly, keeps the slope it learns today.

**Why this priority**: Underfloor heating needs its slow slope (#255).

**Acceptance Scenarios**:

1. **Given** a cycle that rises 1.0 °C/h until its target, **When** it is extracted, **Then** its
   heating slope is 1.0 °C/h, measured up to the cycle end.
2. **Given** a cycle that rises 0.3 °C/h for four hours until its target, **When** it is
   extracted, **Then** its heating slope is 0.3 °C/h.
3. **Given** a cycle whose last 40 minutes are flat, **When** it is extracted, **Then** its
   heating slope is measured up to the cycle end.

### User Story 3 — Split cycles get the slope of the rise (Priority: P2)

**Acceptance Scenarios**:

1. **Given** heating cycles split every 30 minutes and a plateau cycle, **When** it is extracted,
   **Then** every sub-cycle has the slope of the rise, and the last one ends where the heating
   phase ends.

### Edge Cases

- A plateau starting at the end of the dead time: slope 0, cycle not learned.
- A reading that cannot be parsed is ignored when looking for the plateau.
- Sensor jitter below 0.1 °C during the plateau does not end it.
- A cycle cached before the field was recorded: full window, as today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The extraction MUST record, for each cycle, when its heating phase ends and the
  temperature of that reading, if a plateau is found within the cycle.
- **FR-002**: A plateau MUST be the first reading of the heating phase after which the room gains
  less than `PLATEAU_RISE_TOLERANCE_C` for at least `PLATEAU_MIN_DURATION_MINUTES`, all within the
  cycle.
- **FR-003**: `avg_heating_slope` MUST measure the rise from the start of the heating phase to its
  end when the end is recorded, and to the cycle end otherwise.
- **FR-004**: The cycle start, end, end temperature, dead time, disturbance status and slot MUST
  stay as today.
- **FR-005**: Sub-cycles MUST cover the heating phase up to its end and MUST NOT carry the end of
  their parent's heating phase.
- **FR-006**: The cycle cache MUST store the end of the heating phase and read cycles stored
  without it as having none.
- **FR-007**: The domain layer MUST stay free of Home Assistant imports.

### Key Entities

- **HeatingCycle**: gains `plateau_start_time` and `plateau_start_temp` (both optional, recorded
  by the extraction), and the `heating_phase_end_time` / `heating_phase_end_temp` properties: the
  plateau start when recorded, else the cycle end.

## Success Criteria *(mandatory)*

- **SC-001**: On the 2026-11-05 bathroom history, the cycle slope is about 0.8 °C/h instead of
  0.22 °C/h.
- **SC-002**: The living room (underfloor) cycles of 2026-11-04 and 2026-11-05 keep their slope.
- **SC-003**: The existing cycle, dead time and slope tests pass unchanged.

## Plan

- `domain/constants.py`: add `PLATEAU_RISE_TOLERANCE_C = 0.1` and
  `PLATEAU_MIN_DURATION_MINUTES = 60`.
- `domain/value_objects/heating.py`: add the two optional fields and the `heating_phase_end_*`
  properties used by `avg_heating_slope`, and document them.
- `domain/services/heating_cycle_service.py`: `_find_heating_phase_end` scans the indoor readings
  from the end of the dead time to the cycle end and returns the first plateau reading.
  `_create_cycles` records it; `_split_into_cycles` splits up to it and clears it on sub-cycles.
- `infrastructure/adapters/heating_cycle_storage.py`: serialise and deserialise the two fields.

## Tasks

1. design: this specification.
2. test: BDD feature `plateau_heating_slope.feature` (stories 1–3) and unit tests for the plateau
   search, the slope window, the split and the storage round trip.
3. fix: constants, value object, extraction, split, storage.
4. docs: CHANGELOG and the user documentation of the learned slope.
