---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Drive the climate at the anticipated start

**Feature Branch**: `281-drive-climate-at-anticipated-start`
**Created**: 2026-11-14
**Status**: Draft
**Input**: User description: "IHP applies the next slot's own action (preset or temperature) directly to the climate entity at the anticipated start, for any scheduler it can read, while respecting each scheduler's own rules (#249, #232)"

## Principle

The scheduler decides what happens, when, and whether it happens. IHP only decides how early.
At the anticipated start, IHP applies the next slot's own action to the climate entity. At the
slot time, the scheduler applies the same action, which changes nothing.

This replaces the earlier rule "IHP computes, something else actuates" (#232).

## Clarifications

### Session 2026-11-14

- Q: Where does the opt-in for direct control of native schedules apply? → A: One setting per IHP instance (per VTherm), covering all its native schedules.
- Q: What does IHP apply when a native block carries both a preset and a temperature? → A: The preset is applied; the temperature only feeds the anticipation calculation.
- Q: What happens when a command has no effect on the climate? → A: Nothing is marked active; IHP retries at each recalculation and logs the reason once per slot.
- Q: What happens to the recorded state when the slot time arrives? → A: It is discarded without restoring; the next slot records a new one.

## User Scenarios & Testing *(mandatory)*

Constitution-driven test requirements:

- Every user story MUST include at least one BDD scenario written in Gherkin.
- Every user story MUST define technical validation for the failure, boundary, or
  algorithmic risks that are actually relevant to that story.

### User Story 1 - No errors for schedulers IHP cannot actuate (Priority: P1)

A user whose schedules come from Climate Scheduler (its switches imitate the HACS Scheduler
format) or from any other entity IHP cannot actuate sees IHP compute the anticipation without
any error in the logs. Today IHP identifies a scheduler by the look of its attributes, so it
sends HACS-only commands to entities that cannot receive them.

**Why this priority**: it fixes an error raised on every start attempt, it is small, and every
later story needs IHP to know which scheduler owns an entity.

**Independent Test**: configure a Climate Scheduler switch; trigger a recalculation inside the
preheating window; check that no error is logged and the anticipation sensors are updated.

**Acceptance Scenarios**:

1. **Given** a schedule entity owned by Climate Scheduler and HACS Scheduler not installed,
   **When** the anticipated start is reached, **Then** no HACS command is sent and no error is logged.
2. **Given** a schedule entity owned by HACS Scheduler, **When** the anticipated start is
   reached, **Then** behavior is exactly as today.
3. **Given** an entity from an unknown scheduler, **When** a recalculation runs, **Then** the
   anticipation is computed and exposed, and nothing is actuated.

```gherkin
Feature: Scheduler ownership
  Scenario: A Climate Scheduler switch is never sent a HACS command
    Given a schedule switch owned by Climate Scheduler
    And HACS Scheduler is not installed
    When the anticipated start is reached
    Then no scheduler command is sent
    And no error is logged
    And the anticipated start sensor shows the computed time
```

**Technical validation**: ownership resolved from the entity's registered platform, not its
attributes; missing registry entry falls back to compute-only; HACS path regression tests.

---

### User Story 2 - Native schedule users get a real preheat (Priority: P2)

A user whose heating plan is a native Home Assistant `schedule` helper opts in to direct
control, once for the whole IHP instance. At the anticipated start, IHP applies the next block's action to the climate entity.
The action comes from the block's extra data (keys configurable, defaulting to `preset` and
`temperature`). When the block has none of these keys, IHP applies a configured fallback preset
(`comfort` by default). Without opting in, behavior is unchanged: compute only.

**Why this priority**: it is the original #232 need, and the first real direct-drive slice.

**Independent Test**: opt in with a native schedule whose next block carries `preset: comfort`;
reach the anticipated start; check the climate holds the comfort preset.

**Acceptance Scenarios**:

1. **Given** opt-in and a next block with `preset: comfort`, **When** the anticipated start is
   reached, **Then** the climate is set to the comfort preset.
2. **Given** opt-in and a next block with `temperature: 21`, **When** the anticipated start is
   reached, **Then** the climate target becomes 21 °C.
3. **Given** opt-in and a block with no known key, **When** the anticipated start is reached,
   **Then** the fallback preset is applied.
4. **Given** no opt-in, **When** the anticipated start is reached, **Then** nothing is actuated.
5. **Given** opt-in and a block carrying both `preset: comfort` and `temperature: 21`,
   **When** the anticipated start is reached, **Then** the comfort preset is applied, and 21 °C is
   used only to compute the anticipation.
6. **Given** two adjacent ON blocks with different data, **When** the first is running,
   **Then** the second is still anticipated with its own action.

```gherkin
Feature: Native schedule preheating
  Scenario: The next block's preset is applied at the anticipated start
    Given direct control is enabled for a native schedule
    And the next block carries the data preset "comfort"
    When the anticipated start is reached
    Then the climate preset becomes "comfort"
```

**Technical validation**: block data read for the next block (not only the running one);
non-scalar or missing data; keys with unexpected types; day rollover and cross-midnight blocks.

---

### User Story 3 - The action is applied faithfully and undone safely (Priority: P2)

Whatever the scheduler, a preset slot is applied as a preset and a temperature slot as a
temperature. Before acting, IHP records the climate's state. If the preheat is cancelled (slot
removed or moved, scheduler disabled, IHP switched off), IHP returns the climate to the recorded
state, unless the user or another automation changed it meanwhile. The record survives a
restart and an integration reload.

**Why this priority**: direct control is only acceptable if it can never leave the room in a
state the user did not choose.

**Independent Test**: start a preheat, remove the slot, check the recorded state is restored;
repeat after changing the preset by hand, check nothing is restored.

**Acceptance Scenarios**:

1. **Given** a running preheat, **When** the slot is removed, **Then** the recorded state is restored.
2. **Given** a running preheat, **When** the user changes the preset by hand and the slot is
   then removed, **Then** IHP restores nothing.
3. **Given** a running preheat, **When** Home Assistant restarts, **Then** the record is
   kept and the preheat continues or is cleanly cancelled.
4. **Given** the climate was already in an override before the preheat, **When** the preheat is
   cancelled, **Then** the climate returns to that override.
5. **Given** a slot due within a few minutes, **When** a cancellation happens, **Then** IHP
   treats it as a completion and restores nothing, because the scheduler is about to apply
   the same action.
6. **Given** a running preheat, **When** the slot time arrives, **Then** the recorded state is
   discarded without any restoration, and the next slot records a new one.

```gherkin
Feature: Safe restore
  Scenario: A manual change during the preheat is never overwritten
    Given a preheat is running and the previous state was recorded
    And the user selects another preset by hand
    When the preheat is cancelled
    Then the climate keeps the user's preset
```

**Technical validation**: state recorded once per slot, before the first write; comparison on
the thermostat's requested state, not on values altered by safety, window or load shedding; a
change from another context ends IHP's claim on the state; re-entry after restart must not
record IHP's own state as the previous one.

---

### User Story 4 - Climate Scheduler users get a real preheat (Priority: P3)

A user of Climate Scheduler sees the room preheated at the anticipated start with the next
node's action, applied directly, with no extra automation.

**Why this priority**: it was the request in discussion #74, and it reuses stories 1 to 3.

**Independent Test**: with a Climate Scheduler schedule, reach the anticipated start of the
next node; check the climate holds the node's action; at the node time check nothing changes.

**Acceptance Scenarios**:

1. **Given** a Climate Scheduler switch that is enabled, **When** the anticipated start is
   reached, **Then** the next node's action is applied to the climate entity.
2. **Given** a disabled switch, **When** the anticipated start would be reached, **Then**
   nothing is applied.
3. **Given** the scheduler re-applies its current node after a restart, **When** that
   undoes the preheat, **Then** IHP treats it as a change by another party: it does not
   fight it, restores nothing, and the slot is reached normally.

```gherkin
Feature: Climate Scheduler preheating
  Scenario: The next node is applied early
    Given an enabled Climate Scheduler switch whose next node sets 21 degrees
    When the anticipated start is reached
    Then the climate target becomes 21 degrees
```

**Technical validation**: node selection for groups, entities with several nodes, and after
midnight; nodes with an unchanged ("no change") temperature are not driven.

---

### Edge Cases

- The climate is `off`, or IHP's switch is off, or the room is already at target: nothing is done.
- The slot is on another day than the anticipated start (cross-midnight): the slot's own date is used.
- Several schedulers feed the same climate: the earliest slot wins, as today.
- A preset the climate does not offer: nothing is applied, and the reason is logged.
- A VTherm with a manual-override duration configured receives a temperature slot: IHP applies
  it anyway, and the documentation warns that VTherm may revert it after that duration.
- Two start attempts for the same slot happen at once (timer and recalculation): the state is
  recorded once and the action is applied once.
- The climate refuses the command silently (lock, central mode): the missing effect is
  detected, the preheat is not reported active, IHP retries at each recalculation and logs
  the reason once per slot.
- A schedule entity that does not set anything itself (native schedule): nothing reverts the
  climate after the slot unless the user has an automation for it; this is documented.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST identify which scheduler owns an entity from its registered platform.
- **FR-002**: System MUST keep the HACS Scheduler path unchanged: delegation to its run-action
  command, the existing verification and the next-scheduler fallback.
- **FR-003**: System MUST apply a preset slot as a preset and a temperature slot as a
  temperature, never converting one into the other.
- **FR-004**: System MUST apply the action only to the climate entity IHP is configured for,
  so that each room has its own anticipation.
- **FR-005**: System MUST record the climate's state once per slot before the first write, even
  when two start attempts for the same slot happen at once, keep
  it across restart and reload, and restore it on cancellation only if the climate is still
  in the state IHP set. It MUST restore only the preset or temperature IHP changed, never the
  HVAC mode. It MUST discard the record, without restoring, when the slot time arrives.
- **FR-006**: System MUST define clear domain/infrastructure boundaries consistent with
  hexagonal architecture and DDD: the domain expresses "apply the slot's action" and
  "restore"; which service an integration offers stays in infrastructure.
- **FR-007**: System MUST NOT add new Home Assistant events; state it in the plan and reuse the
  existing state listeners.
- **FR-008**: System MUST provide explicit typing for all public interfaces, with the slot's
  action as an immutable value.
- **FR-009**: System MUST log, at INFO, each application and each restoration with the device
  friendly name, and at DEBUG the reasons for skipped actions.
- **FR-010**: System MUST remain stateless in the domain; the only persisted state is the
  per-slot record, and the plan MUST justify where it lives.
- **FR-011**: System MUST make direct control of native schedules an explicit opt-in, set once
  per IHP instance and applying to all its native schedules, with configurable data keys and a
  fallback preset.
- **FR-012**: System MUST send climate commands with a context that has a parent, so that
  schedulers that detect manual changes do not treat them as overrides.
- **FR-013**: System MUST check, after each command, that the climate took the requested
  action, and MUST NOT report the preheat active otherwise. It retries at each recalculation
  until the slot time and logs the reason once per slot. For direct drive there is no fallback
  to another scheduler; the HACS fallback stays as today (FR-002).
- **FR-014**: System MUST do nothing for an unsupported scheduler: no command, no error, and
  the anticipation still computed.

### Workflow Requirements *(mandatory)*

- **WR-001**: The specification names `speckit.specify` as producer and `speckit.clarify` as
  the different critical reviewer.
- **WR-002**: `speckit.checklist` reviews the plan, `speckit.analyze` the tasks and
  `speckit.review` the implementation.
- **WR-003**: Any unresolved reviewer challenge MUST be tracked explicitly before
  implementation begins.

### Documentation Requirements *(mandatory)*

- **DR-001**: The user guide MUST explain, per scheduler, who applies the action and the
  opt-in for native schedules, including the VTherm manual-override caveat.
- **DR-002**: `docs/architecture/OVERVIEW.md` MUST state the new principle.
- **DR-003**: All new or updated documentation and code artifacts MUST be in English,
  except `README.fr.md`, which MUST be updated whenever `README.md` changes.
- **DR-004**: Documentation changes MUST avoid duplicated guidance and ad-hoc
  markdown reports unless explicitly requested.

### Key Entities *(include if feature involves data)*

- **Slot action**: what a slot asks of the climate: a preset or a temperature.
- **Scheduled timeslot**: when the slot starts (with its date) and its slot action.
- **Preheat record**: the climate's state before IHP acted, what IHP set, and which slot it was for.
- **Scheduler ownership**: which scheduler integration owns an entity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With Climate Scheduler or an unknown scheduler, zero errors are logged over a full day.
- **SC-002**: With a native schedule and the opt-in, 100% of anticipated starts whose guards
  pass leave the climate in the slot's action within one minute.
- **SC-003**: 100% of preset slots are applied as presets, and 100% of temperature slots as temperatures.
- **SC-004**: After a cancellation without a manual change, farther from the slot than the
  guard window, the climate is back in its recorded state; with a manual change, or inside
  the guard window, IHP never alters it.
- **SC-005**: HACS Scheduler users see no change in behavior (existing tests pass unchanged).

## Out of Scope

- HACS Scheduler direct drive: waits for the condition-evaluation service requested in
  nielsfaber/scheduler-component#551.
- ha-chauffage: its next-change entity is not published yet (#155).
- Any climate entity beyond VTherm (#252), and VTherm's timed preset, which would erase the
  scheduler's own preset at its end.
- Slots that change the HVAC mode.

## Assumptions

- A climate being `off` is a user choice, so IHP leaves it alone.
- Slots in this feature carry a preset or a temperature only.
- The preheat record lives in IHP's existing storage.
- "A few minutes" before a slot (story 3) is a named constant fixed in the plan.
- Native schedules apply nothing themselves; resetting after the slot is the user's automation.
- Unloading or reloading the integration keeps the preheat record; it is reconciled at the next start.
- A change of the climate's requested state after IHP acted is final for that slot: IHP never
  tells a scheduler's own re-application from a user's change, so it never fights either.
