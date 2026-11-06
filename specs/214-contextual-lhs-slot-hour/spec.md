---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Slot Learns From the Cycles That Reached Its Target Around It

**Feature Branch**: `fix/issue-214-contextual-lhs-slot-hour`
**Created**: 2026-10-31
**Status**: Draft
**Input**: GitHub issue #214 — "Contextual LHS: cycles ending just before a slot are filed under
the previous hour"

## Context

IHP learns a **contextual LHS** for each hour of the day: the average heating slope of the
cycles filed under that hour. Since #183, the two sides of this lookup use the same key:

- **Write side**: `ContextualLHSCalculatorService.extract_hour_from_cycle` files a cycle under
  the local hour in which it **ends** (`end_time.hour`), i.e. when the target was reached.
- **Read side**: the anticipation reads the hour of the scheduled slot (`target_time.hour`), and
  so do the Contextual Learned Heating Slope sensor and the cache it reads
  (`next_schedule_time.hour`).

Both sides take the hour as is, so the hour of a whole-hour slot runs from the slot to the
next hour. Preheating aims to reach the target at the slot, but a cycle **ends before** it
by construction:

- The cycle extraction ends a cycle once the room is within the detection threshold
  (`temp_delta_threshold`, 0.2 °C by default) of the target.
- The anticipation deliberately starts a little early: the first 0.2 °C is counted in both the
  dead time and `Δ / LHS` (#245).

With a perfectly learned room, a cycle for a 07:00 slot ends about `0.4 °C / LHS` before it:
12 min at 2 °C/h, 24 min at 1 °C/h. A cycle ending at 06:58 is filed under 06:00, the 07:00
slot reads 07:00 and never sees it. Only cycles that land on or after the slot are learned for
it, so the learned slope depends on how precisely preheating lands.

## Clarifications

### Session 2026-10-31

- Q: Should cycles be keyed by the nearest hour, or should each cycle record the slot it served?
  → A: The nearest hour. Cycles are rebuilt from the Recorder history of the thermostat, which
  holds no trace of the slot a cycle was aimed at; cycles already cached have none either.
- Q: Which hour does a moment exactly on the half hour belong to? → A: The earlier hour. Cycles
  end before their slot rather than after it, so a 06:30 slot must read the hour that holds the
  cycles that ended in the half hour before it. A time from `h:00` up to and including `h:30`
  belongs to hour `h`; a time after `h:30` belongs to hour `h+1`.
- Q: Only the write side? → A: No, both sides use the same rule (#183). Rounding cycle ends
  while slots keep their hour as is would put a cycle that ends exactly on a 06:45 slot under
  07:00 while the slot reads 06:00: a perfect landing would never be learned. With one rule, a
  cycle that ends exactly at its slot is always read by that slot.
- Q: Which slots read a different hour after the change? → A: Only slots after the half hour
  (`h:31` to `h:59`), which now read hour `h+1`. Slots from `h:00` to `h:30` keep reading hour
  `h`; what changes for them is which cycles fill that hour:

  | Slot | Cycles read today (end time) | Cycles read after the change (end time) |
  |---|---|---|
  | 07:00 | 07:00 to 07:59 (up to 59 min late, never early) | after 06:30 up to 07:30 (up to 30 min early or late) |
  | 06:30 | 06:00 to 06:59 (up to 30 min early or 29 min late) | after 05:30 up to 06:30 (up to 60 min early, never late) |
  | 06:45 | 06:00 to 06:59 (up to 45 min early or 14 min late) | after 06:30 up to 07:30 (up to 15 min early or 45 min late) |

  Whole-hour slots, the most common, gain the early cycles they missed. Half-hour slots trade
  late cycles for early ones, which is the side cycles land on.
- Q: The issue asks whether only the last sub-cycle of a split cycle should count for the slot.
  → A: Not in this change. Splitting is disabled by default. A cached sub-cycle carries no link
  to its parent cycle, so telling an intermediate sub-cycle from a short cycle needs a new field
  in the cycle cache. Since #245 every sub-cycle has the slope of the whole heating phase, so the
  slot's hour gets the right slope from the last sub-cycle and from the others that end within
  the half hour before the slot. Intermediate sub-cycles that end earlier still add that slope to
  earlier hours (see Known Limitations).
- Q: What happens to contextual slopes already stored? → A: They were averaged with the old key
  and are kept until the next recalculation of the contextual LHS, after new cycles are
  extracted or old ones are pruned (at most a day), or right away with `reset_learning`. Until
  then, slots after the half hour read the stored value of the next hour.
- Q: What does the sensor show? → A: The slope of the contextual hour of the next slot, and that
  hour in its `scheduled_hour` attribute: `07:00` for a 06:45 slot.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A cycle that reaches the target just before a whole-hour slot counts for it (Priority: P1)

A user has a 07:00 slot. Preheating reaches the target at 06:58. The slope of that cycle is
learned for the 07:00 slot, together with the cycles that reached the target a little after
07:00.

**Why this priority**: This is the defect of issue #214. Cycles land before the slot by
construction, so most preheat cycles of a whole-hour slot are filed under the previous hour.

**Independent Test**: Learn contextual slopes from cycles ending at 06:58 and 07:20, then read
the slope of a 07:00 slot.

**Acceptance Scenarios**:

1. **Given** a cycle that reached the target at 06:58, **When** the slope of a 07:00 slot is
   read, **Then** it is the slope of that cycle.
2. **Given** cycles that reached the target at 06:58 and 07:20, **When** the slope of a 07:00
   slot is read, **Then** it is the average of both.
3. **Given** a cycle that reached the target at 06:20, **When** the slopes are read, **Then** it
   counts for a 06:00 slot and not for a 07:00 slot.

### User Story 2 — A half-hour slot keeps the cycles that reached the target before it (Priority: P1)

A user has a 06:30 slot. The cycles that reach the target in the half hour before 06:30, or
exactly at 06:30, count for it. A cycle that reaches the target after 06:30 counts for the next
hour.

**Why this priority**: Half-hour slots work today for cycles landing early; the change must not
break them.

**Independent Test**: Learn contextual slopes from cycles ending at 06:10, 06:30 and 06:40, then
read the slopes of a 06:30 and a 07:00 slot.

**Acceptance Scenarios**:

1. **Given** cycles that reached the target at 06:10 and at 06:30, **When** the slope of a 06:30
   slot is read, **Then** it is the average of both.
2. **Given** a cycle that reached the target at 06:40, **When** the slopes are read, **Then** it
   counts for a 07:00 slot and not for a 06:30 slot.

### User Story 3 — A cycle just before midnight counts for a midnight slot (Priority: P2)

A user has a 00:00 slot. A cycle that reaches the target at 23:50 counts for it.

**Why this priority**: The nearest hour of a time after 23:30 is on the next day; the hour must
wrap to 0 instead of going out of range.

**Acceptance Scenarios**:

1. **Given** a cycle that reached the target at 23:50, **When** the slope of a 00:00 slot is
   read, **Then** it is the slope of that cycle.

### User Story 4 — The sensor shows the slope the slot uses (Priority: P2)

The Contextual Learned Heating Slope sensor shows the slope of the contextual hour of the next
slot, so it shows what the anticipation uses.

**Acceptance Scenarios**:

1. **Given** the next slot is at 06:45, **When** the sensor is read, **Then** it shows the slope
   learned for 07:00 and its `scheduled_hour` attribute is `07:00`.
2. **Given** the next slot moves from 06:20 to 06:40, **When** the anticipation result is
   received, **Then** the sensor state is written, because the contextual hour changed.

### Edge Cases

- **Exactly on the half hour** (`06:30:00`): hour 6. One microsecond later: hour 7.
- **Seconds**: cycle ends come from the Recorder with seconds; `07:29:59` is hour 7.
- **Timezone**: cycle times are naive UTC and are converted to the local timezone first
  (unchanged); the rule then applies to the local clock. Slot times are already local.
- **Daylight saving time**: the rule only reads the wall clock (hour, minutes, seconds), so it
  does not depend on the length of the day.
- **Slot after 23:30**: hour 0.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The contextual hour of a moment MUST be its hour when it is at most 30 minutes
  past the hour, and the next hour (wrapping 23 to 0) when it is more than 30 minutes past.
- **FR-002**: The contextual LHS MUST file each cycle under the contextual hour of its end time,
  read in the local timezone.
- **FR-003**: The anticipation MUST read the contextual LHS of the contextual hour of the slot.
- **FR-004**: The Contextual Learned Heating Slope sensor, and the cache it reads, MUST use the
  contextual hour of the next slot, for its value, its `scheduled_hour` attribute and the
  detection of a context change.
- **FR-005**: A single domain rule MUST provide the contextual hour to every side.

### Key Entities

- **Contextual hour**: the hour of day (0-23) nearest to a moment, a moment exactly on the half
  hour belonging to the earlier hour. Key of the contextual LHS on both the write and read side.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A cycle ending up to 30 minutes before or after a whole-hour slot is learned for
  that slot (today: only from 0 to 59 minutes after).
- **SC-002**: A cycle ending exactly at its slot is learned for that slot, whatever the minute of
  the slot.
- **SC-003**: Slots from `h:00` to `h:30` keep reading hour `h`.

## Assumptions

- The minute of a slot is the minute at which the target is meant to be reached; the anticipation
  aims for it (unchanged).
- Most slots are on the hour or the half hour.

## Known Limitations

- **Late landings on a half-hour slot**: a cycle that reaches the target after a 06:30 slot is
  learned for 07:00. Fixed hour buckets cannot center both whole-hour and half-hour slots; the
  boundary is put where fewer cycles land.
- **Split cycles**: intermediate sub-cycles ending more than half an hour before the slot still
  add the slope of the heating phase to earlier hours (splitting is disabled by default).
- **Stored contextual slopes**: averaged with the old key until the next recalculation (at most a
  day, or `reset_learning`).
