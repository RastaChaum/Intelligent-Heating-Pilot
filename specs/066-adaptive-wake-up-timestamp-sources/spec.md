---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Adaptive wake-up from timestamp sources

**Feature Branch**: `feature/issue-66-adaptive-wake-up-timestamp-sources`
**Created**: 2026-11-15
**Status**: Draft
**Input**: User description: "Let each IHP take a wake-up time from a timestamp entity (phone next alarm, input_datetime, ...) and preheat so the room reaches the target temperature when it goes off. Issue #66, which also covers #63 (use IHP without a scheduler). Built on the direct climate control of PR #292."

## Clarifications

### Session 2026-11-15

- Q: Hold after the deadline when a scheduler is also configured → A: the hold ends as soon as a slot of that IHP's scheduler is reached; the scheduler takes over and IHP restores nothing.
- Q: Alarm removed after the preheat has started but before the deadline → A: the preheat is cancelled and the previous thermostat state restored, unless someone changed it meanwhile.
- Q: A closer deadline appears while a preheat runs for a later one → A: IHP switches without restoring in between: the recorded initial state is kept and the new deadline and its target apply directly.
- Q: "Target from the schedule" when a scheduler gives only one of the two slots → A: the single readable slot is used only if its temperature is higher than the thermostat's current target temperature; otherwise the fixed target applies (or the source is ignored without one).

## User Scenarios & Testing *(mandatory)*

Constitution-driven test requirements:

- Every user story MUST include at least one BDD scenario written in Gherkin.
- Every user story MUST define technical validation for the failure, boundary, or
  algorithmic risks that are actually relevant to that story.

### User Story 1 - Preheat for an alarm earlier than the schedule (Priority: P1)

A shift worker has a weekly schedule that warms the bedroom at 07:00. On some days the phone alarm is set at 05:30. The user adds the phone's next-alarm entity to that IHP as a wake-up source. IHP now treats 05:30 as the next deadline, computes how long the room needs from its learned heating behavior, and starts heating early enough for the target to be reached at 05:30. Once that deadline has passed, IHP goes back to the schedule.

**Why this priority**: This is the core of issue #66 and needs no new decision rule: the earliest upcoming deadline wins. It removes the "cold start" case.

**Independent Test**: Configure one IHP with a scheduler and a timestamp source, set the source 90 minutes before the schedule's next slot, and check that the anticipated start is computed for the source time and the climate is driven at that start.

**Acceptance Scenarios**:

1. **Given** a schedule slot at 07:00 and a wake-up source at 05:30 with a fixed comfort target, **When** IHP recalculates, **Then** the next deadline is 05:30 and the anticipated start is the time needed before 05:30.
2. **Given** the wake-up deadline has passed, **When** IHP recalculates, **Then** the next deadline is the schedule's next slot again.

```gherkin
Scenario: An alarm earlier than the schedule becomes the next deadline
  Given an IHP with a scheduler whose next slot is at 07:00 and a wake-up source set to 05:30
  And the learned heating slope is 2.0 degrees per hour and the room is 4 degrees below the target
  When IHP recalculates the anticipation
  Then the next deadline is 05:30
  And the anticipated start is about two hours before 05:30
```

**Technical validation**: unit tests for deadline selection among several sources (earliest wins, ties, source time equal to now), and for a deadline that has just passed.

---

### User Story 2 - Wake-up source only, no scheduler (Priority: P1)

A user with an irregular life (issue #63: house modes, no scheduler) configures an IHP with no scheduler and only a wake-up source. IHP applies the source's target to the thermostat at the anticipated start, so the room is ready at the wake-up time. The user may set a hold duration: that long after the wake-up time, IHP puts the thermostat back in the state it was in before the preheat, provided nobody changed it meanwhile. Without a hold duration, IHP leaves the thermostat alone after the wake-up time.

**Why this priority**: This is the only way to solve the "alarm later than the schedule, no heating of an empty room" case, because a scheduler cannot be stopped from firing by IHP. It also answers #63. Without the hold, a room with no scheduler would stay at the comfort setting indefinitely.

**Independent Test**: Configure an IHP with only a timestamp source and a fixed target; verify the thermostat receives the target at the anticipated start, and is restored after the hold duration.

**Acceptance Scenarios**:

1. **Given** no scheduler and a wake-up source with a fixed preset target, **When** the anticipated start is reached, **Then** the climate entity is set to that preset.
2. **Given** a hold duration of 90 minutes, **When** 90 minutes have passed since the wake-up time and nobody changed the thermostat, **Then** it returns to its pre-preheat state.
3. **Given** a hold duration, **When** the user changed the thermostat by hand during the hold, **Then** IHP does not overwrite that change.
4. **Given** no hold duration, **When** the wake-up time has passed, **Then** IHP sends nothing more.
5. **Given** a hold duration and a scheduler on the same IHP, **When** a slot of that scheduler is reached during the hold, **Then** the hold ends and IHP restores nothing.

```gherkin
Scenario: A wake-up source drives the thermostat without any scheduler
  Given an IHP with no scheduler and a wake-up source set to 06:30 with the comfort preset as target
  When the anticipated start time is reached
  Then the thermostat is set to the comfort preset
  And the room is expected to reach the target temperature at 06:30
```

**Technical validation**: unit tests for restore only when untouched, restore after a restart during the hold, and a hold duration of zero or absent.

---

### User Story 3 - Target taken from the schedule (Priority: P2)

A user who also has a schedule does not want to repeat its temperatures. On the wake-up source the user picks "target from the schedule". IHP uses the target of the schedule slot that follows the wake-up time (for instance the 07:00 comfort slot when the alarm is at 05:30), unless the slot in effect at the wake-up time asks for a higher temperature (for instance an alarm at 08:00 during a comfort block that ends at 09:00 before an eco slot): the target is never lower than what the schedule already asks for at that moment. If the schedule cannot provide one, IHP uses the source's fixed target when the user gave one; otherwise the source is ignored and the reason is logged.

**Why this priority**: It saves duplicate configuration and keeps one place for temperatures, but US1 and US2 work without it.

**Independent Test**: Configure a source with "from schedule" and a different fixed target; check that the schedule's temperature is used when readable, the fixed one when not, and that with neither the source is ignored with a log line.

**Acceptance Scenarios**:

1. **Given** a source set to "target from schedule" and a schedule whose slot after the source time asks for 21 degrees, **When** IHP anticipates, **Then** the target is 21 degrees.
2. **Given** the same source with a fixed fallback target and a schedule that gives no slot after that time, **When** IHP anticipates, **Then** the fallback target is used.
3. **Given** "from schedule", no fallback and no usable slot, **When** IHP anticipates, **Then** the source is ignored and a warning explains why.
4. **Given** a source set to "target from schedule", the slot in effect at the wake-up time asking for 21 degrees and the next slot after it asking for 17 degrees, **When** IHP anticipates, **Then** the target is 21 degrees.
5. **Given** "from schedule" and a scheduler that exposes only the following slot, **When** that slot's temperature is higher than the thermostat's current target, **Then** it is used; **When** it is not higher, **Then** the fixed target is used, or the source is ignored without one.
6. **Given** "from schedule" but no scheduler configured on that IHP, **When** the options are saved, **Then** IHP uses the fixed target, or refuses the configuration if there is none.

```gherkin
Scenario: The wake-up target is read from the schedule
  Given a wake-up source at 05:30 set to take its target from the schedule
  And the schedule's next slot after 05:30 is at 07:00 for 21 degrees
  When IHP recalculates the anticipation
  Then the target temperature is 21 degrees
  And the deadline is 05:30
```

```gherkin
Scenario: The wake-up target is never lower than the slot already in effect
  Given a wake-up source at 08:00 set to take its target from the schedule
  And the schedule asks for 21 degrees from 06:00 and for 17 degrees from 09:00
  When IHP recalculates the anticipation
  Then the target temperature is 21 degrees
```

**Technical validation**: unit tests for each fallback branch, for the in-effect versus following slot comparison (including preset-only slots compared through the temperature the thermostat publishes), for a scheduler that only exposes a short look-ahead, and for a preset-only slot whose temperature the thermostat publishes.

---

### User Story 4 - Robust to a moving or invalid timestamp (Priority: P2)

Alarms move: snooze, edit, dismissal, a new alarm set. The entity can also be unknown, unavailable, in the past or days away. IHP must neither heat for a bogus value nor flap.

**Why this priority**: Without it the feature is unsafe to leave running unattended.

**Independent Test**: Feed a source a sequence of values (valid, snoozed, unknown, past, beyond horizon) and check the resulting deadlines and that a preheat in progress follows the change.

**Acceptance Scenarios**:

1. **Given** a preheat in progress for 05:30, **When** the alarm is snoozed to 05:40, **Then** the anticipation is recalculated for 05:40 without the thermostat going back and forth.
2. **Given** a value that is unknown, unavailable, in the past or beyond the horizon (24 hours by default), **When** IHP reads it, **Then** the source gives no deadline and nothing is actuated.
3. **Given** the alarm is removed or dismissed before the deadline, whether before or after the preheat started, **When** the entity changes, **Then** the preheat is cancelled and the thermostat restored, unless someone changed it meanwhile.
4. **Given** a preheat is running for a later deadline and a closer valid deadline appears, **When** IHP recalculates, **Then** it switches to the closer deadline and its target without restoring the thermostat in between.
5. **Given** the alarm goes off and the entity moves to the next day's alarm, **When** the preheat has just reached its deadline, **Then** it is not cancelled.

```gherkin
Scenario: A snoozed alarm moves the deadline
  Given a preheat in progress for a 05:30 wake-up
  When the alarm entity changes to 05:40
  Then IHP recalculates for 05:40
  And the thermostat is not set back to its previous state in between
```

**Technical validation**: unit tests for every invalid value kind, time zones (aware and naive values), and the ordering of an entity change against a deadline being reached.

---

### Edge Cases

- Several wake-up sources on one IHP (alarm and arrival time): the earliest valid one wins, per recalculation.
- The same entity used by several IHP instances (one per room): each uses its own target and hold duration.
- A wake-up deadline later than a schedule slot: the schedule slot is still the next deadline and its scheduler still fires on its own. IHP cannot stop a scheduler; the documentation tells users to disable or condition the schedule, or to use the source alone.
- A source time earlier than the minimum lead already needed (the room cannot be ready in time): same behavior as a late schedule slot today.
- The entity is a date-only or time-only value: not usable as a deadline, ignored and logged once.
- Home Assistant restarts during a preheat or a hold: the state recorded by direct control is reconciled as for schedulers.
- Source time and a schedule slot at the same minute: the schedule slot wins, so a single target applies.
- The thermostat is switched off: nothing is applied and its heating mode is never changed, as for schedulers (#249).
- The thermostat does not publish the temperature of a preset target: a default temperature feeds the anticipation, as for native schedules, and the preset is still the one applied.
- IHP is disabled, or the source is removed from the configuration, during a preheat or a hold: it ends as a cancellation (previous state restored unless someone changed it meanwhile).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each IHP MUST accept zero or more wake-up sources, in addition to its schedulers; a source is an entity that holds a point in time (a timestamp sensor, a date-time helper or a date-time entity).
- **FR-002**: IHP MUST pick, at every recalculation, the earliest valid upcoming deadline among all its schedulers and wake-up sources, with no priority setting.
- **FR-003**: A wake-up source MUST give no deadline when its value is unknown, unavailable, not a full date and time, in the past, or further away than a per-source horizon (default 24 hours).
- **FR-004**: A wake-up source MUST have an optional fixed target: a preset or a temperature.
- **FR-005**: A wake-up source MUST be configurable to take its target from the schedule, when at least one scheduler is configured on that IHP. The target is that of the first schedule slot following the wake-up time, but never lower than the target of the slot in effect at the wake-up time; when both exist, the higher temperature wins, and a preset slot is compared through the temperature the thermostat publishes for that preset. When a scheduler exposes only one of the two slots, that slot is used only if its temperature is higher than the thermostat's current target temperature, otherwise FR-006 applies.
- **FR-006**: When the schedule cannot provide a target, IHP MUST use the source's fixed target if any, otherwise ignore the source and log the reason once per change.
- **FR-007**: The configuration MUST refuse a source that has neither a fixed target nor a usable "from schedule" setting.
- **FR-008**: IHP MUST compute the anticipated start for a source deadline with the same learned heating behavior and corrections as for a schedule slot.
- **FR-009**: At the anticipated start, IHP MUST apply the source's target to the climate entity itself, as a preset when the target is a preset and as a temperature otherwise, following the direct-control rules of #249 (record once, restore only if untouched, no change of heating mode).
- **FR-010**: A wake-up source MUST offer an optional hold duration. When set, IHP MUST restore the pre-preheat state that long after the deadline unless it was changed by someone else or a slot of a scheduler of that IHP was reached in the meantime (the scheduler then owns the setting and the hold ends without any restore); when absent, IHP MUST send nothing after the deadline.
- **FR-011**: A change of a source's value MUST trigger a recalculation, and someone else's change to the thermostat after IHP acted MUST stay final for that wake-up, including after its deadline moves (a snooze never makes IHP apply the target again over a manual change); a preheat in progress MUST follow a moved deadline or a closer new one (keeping the recorded initial state, with no restore in between) or be cancelled (with the previous state restored unless someone changed it meanwhile) when the deadline disappears before it is reached, without flapping.
- **FR-012**: Preheats driven by a source MUST feed the same learning as schedule-driven ones; no separate learning path.
- **FR-013**: Sources MUST be added, changed and removed through the integration's options, per IHP (an existing IHP can gain a source at any time; the creation step is unchanged), with translations kept in parity.
- **FR-014**: IHP MUST keep working unchanged for every existing configuration without a wake-up source.
- **FR-015**: The feature MUST keep the domain free of Home Assistant imports, with all external reads and writes behind interfaces, public interfaces typed, and logging per the project conventions (friendly names, INFO for actions taken).
- **FR-016**: The feature MUST introduce no shared mutable state beyond what direct control already records.

### Workflow Requirements *(mandatory)*

- **WR-001**: Producer agent: `speckit.specify`. Critical reviewer: `speckit.clarify`.
- **WR-002**: Plan reviewed by `speckit.checklist`, tasks by `speckit.analyze`, implementation by `speckit.review`.
- **WR-003**: Any unresolved reviewer challenge MUST be tracked explicitly before implementation begins.

### Documentation Requirements *(mandatory)*

- **DR-001**: User documentation MUST cover: adding a source, the earliest-wins rule, the target options, the hold duration, and the limit that a scheduler cannot be stopped by IHP (with the recommended setups).
- **DR-002**: Contributor documentation MUST record the new kind of deadline source in the architecture overview.
- **DR-003**: All artifacts in English except `README.fr.md`, updated with `README.md`.
- **DR-004**: CHANGELOG `[Unreleased]` MUST list the feature; no ad-hoc markdown reports.

### Key Entities *(include if feature involves data)*

- **Wake-up source**: an entity holding a point in time, with an optional fixed target (preset or temperature), a target mode (fixed or from the schedule), a horizon and an optional hold duration; belongs to one IHP.
- **Deadline**: the instant a target must be reached, from a scheduler slot or a wake-up source, carrying its target and where it came from.
- **Target**: a preset or a temperature to apply and to anticipate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the same room state, the anticipated start computed for a source deadline is identical to the one computed for a schedule slot with the same time and target.
- **SC-002**: An IHP with only a wake-up source and no scheduler can be configured and drives its thermostat without any other setup.
- **SC-003**: Invalid, stale or too-distant values produce zero commands sent to the thermostat.
- **SC-004**: A snooze or alarm edit never causes more than one restore for the same wake-up, and no command when the thermostat already holds the target.
- **SC-005**: Every existing configuration behaves identically before and after the change (existing tests pass unchanged).

## Assumptions

- Users who want "no heating for a later alarm" either use the source alone or condition their scheduler; IHP does not control other integrations' timing.
- The 24-hour horizon follows the proposal in issue #66 and is adjustable per source.
- The hold duration is off by default, so existing behavior never changes silently.
- A schedule may expose only a limited look-ahead; "target from the schedule" is best effort and falls back as in FR-006.
- Builds on PR #292 (direct control, per-scheduler actuation); this feature is delivered in a separate PR stacked on it, for release 0.8.0.
- Issue #63 is considered covered by User Story 2; an arrival-time source works the same way with a timestamp entity.
- Calendar entities and a target read from another entity are out of scope for this version.
