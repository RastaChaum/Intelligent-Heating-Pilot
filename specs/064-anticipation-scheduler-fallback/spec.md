---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Anticipation Falls Back When a Scheduler's Conditions Block It

**Feature Branch**: `fix/issue-64-anticipation-scheduler-fallback`
**Created**: 2026-10-26
**Status**: Draft
**Input**: GitHub issue #64 — "Anticipation selects next timeslot from scheduler with unmet
conditions; run_action does nothing → late start"

## Context

A household can configure several scheduler entities for the same room (for example a
"Non-vacation" calendar and a "Vacation" calendar). IHP always anticipates the *earliest*
upcoming timeslot across every configured scheduler, with no way to know whether that
particular scheduler will actually be allowed to act. If the household is on vacation but
the "Non-vacation" scheduler happens to have the earlier timeslot, IHP anticipates and
triggers that scheduler — whose own conditions (configured by the household in the HACS
Scheduler integration) block the action. Nothing reports this back to IHP, so the room stays
cold until the "Vacation" scheduler's own, later timeslot arrives on its own.

This was confirmed against the upstream HACS Scheduler integration: conditions attached to a
timeslot are never exposed through the entity's state (only `next_trigger`, `next_slot`,
`actions`, `timeslots`, `weekdays`, `tags` are). There is no way to know in advance, from
Home Assistant's public state, whether a future timeslot's conditions will hold. IHP can only
learn that an anticipated action had no effect by observing the result after the fact.

## Clarifications

### Session 2026-10-26

- Q: Just after triggering `run_action`, if IHP cannot read the VTherm's resulting state at
  all (entity unavailable/unknown) to verify the effect, what should it do? → A: Treat it as
  success and do not fall back — an unreadable state cannot prove the action failed, and
  disturbing a scheduler that may have actually succeeded (because of a transient read
  failure) is worse than occasionally missing a real failure in this rare, transient case.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Preheating still starts on time when the earliest scheduler is blocked (Priority: P1)

A household has two scheduler entities feeding the same room: "Non-vacation" (target 20°C at
06:30) and "Vacation" (target 20°C at 08:30). Today is a vacation day, so the "Non-vacation"
scheduler's own conditions will not let it run. IHP must still have the room at 20°C by
whichever slot can actually fire, instead of leaving it cold until 08:30 regardless of the
anticipation it calculated for 06:30.

**Why this priority**: This is the exact late-start defect reported in issue #64 — the
anticipation feature silently fails to deliver its core promise (room at temperature on
time) for a configuration pattern (multiple schedulers routed by a condition) that the
scheduler integration explicitly supports.

**Independent Test**: Configure the two schedulers above with the vacation condition active,
let IHP compute and trigger anticipation for 06:30, and verify the room still reaches 20°C
for a schedule the household actually has active that day, without waiting for the missed
slot to elapse first.

**Acceptance Scenarios**:

1. **Given** two schedulers are configured and the earliest one's conditions will not hold
   today, **When** IHP triggers its anticipated action for that earliest timeslot, **Then**
   IHP must detect that the action had no effect and must anticipate and trigger the next
   applicable scheduler's own timeslot instead, without waiting for the blocked timeslot's
   time to pass.
2. **Given** the earliest scheduler's action is correctly applied (its conditions hold),
   **When** IHP triggers it, **Then** IHP must recognize success and must not attempt any
   fallback.
3. **Given** every configured scheduler is blocked for today, **When** IHP exhausts all
   candidates, **Then** IHP must stop retrying for this cycle, leave the thermostat in its
   current state, and make the unresolved situation observable (log/sensor), rather than
   retrying indefinitely or guessing a temperature on its own.

---

### User Story 2 — A single scheduler is never affected by this change (Priority: P2)

A household with only one scheduler entity configured must see no change in behavior:
anticipation and triggering continue exactly as before.

**Why this priority**: Protects the common single-scheduler setup from any regression while
the multi-scheduler fallback is added.

**Independent Test**: With one scheduler configured, verify anticipation and triggering
behave identically before and after this change, including when that single scheduler's own
conditions block the action (no fallback candidate exists, so IHP stops after the single
attempt, per Scenario 3 above).

**Acceptance Scenarios**:

1. **Given** only one scheduler entity is configured, **When** its action is applied
   normally, **Then** behavior is unchanged from before this fix.

---

### User Story 3 — Native HA schedule entities are unaffected (Priority: P3)

A household using a native Home Assistant `schedule.*` helper (no HACS Scheduler) continues
to get anticipation computed and exposed as sensors only, with no actuation attempt and
therefore nothing to fall back from.

**Why this priority**: IHP's established role is to compute, not to actuate directly,
outside of delegating to the HACS Scheduler; native schedules must stay on that path per the
existing design decision ([[ihp-computes-not-actuates]]).

**Independent Test**: Configure only a native `schedule.*` entity and confirm anticipation is
computed and exposed exactly as today, with no new behavior introduced by this feature.

**Acceptance Scenarios**:

1. **Given** only a native `schedule.*` entity is configured, **When** anticipation is
   calculated, **Then** no fallback logic is exercised and no actuation is attempted, exactly
   as today.

---

### Edge Cases

- What happens when the fallback candidate's own anticipated start time is later than "now"
  (the moment the blocked attempt was discovered)? The fallback must be scheduled for its own
  correct anticipated start, not triggered immediately.
- What happens when the fallback candidate's own action is *also* blocked? Per Scenario 3,
  IHP exhausts all remaining enabled candidates for that cycle and then stops, surfacing the
  unresolved state rather than looping.
- How is a scheduler whose action was just confirmed blocked excluded from selection, and for
  how long? **Resolved**: the exclusion is scoped to the current recalculation cycle only.
  The next periodic recalculation re-attempts the earliest scheduler first (it is given a
  fresh chance in case its condition changed) and only falls back again if it is still
  blocked. No exclusion state is persisted across recalculation cycles.
- What happens when two schedulers' timeslots resolve to literally the same target time and
  temperature (duplicate configuration)? Both are distinct candidates and must still be tried
  in order if needed.
- What happens when the climate entity's state cannot be read at all right after triggering
  (unavailable/unknown)? **Resolved**: treated as an unproven failure — IHP does not fall
  back (see Clarifications).
- What happens on the *next* recalculation tick while a fallback is still actively
  preheating, given the earliest scheduler is recomputed fresh each cycle? **Found during
  implementation**: the pre-existing "revert an active preheat whose slot is no longer the
  next one" safeguard would otherwise fire every such tick, reverting the working fallback
  moments before re-confirming it — reintroducing the comfort/eco flapping bug fixed once
  already (#182). Fixed: that safeguard no longer reverts while the active scheduler remains
  enabled, only when it is genuinely no longer usable. See contracts/interfaces.md §8 for the
  accepted, display-only trade-off this introduces (the anticipation sensor's
  `scheduler_entity`/`next_schedule_time` can briefly show the earliest, still-blocked
  candidate instead of the actually-running fallback on such a tick — no actuation effect).
- How does the household learn that every candidate was blocked (Scenario 3)? **Resolved**:
  both a WARNING log entry (identifying the scheduler by `friendly_name`, per the project's
  logging conventions) and a dedicated, dashboard-visible signal (sensor/attribute) are
  required — the household must not have to read logs to learn that anticipation could not
  be delivered this cycle.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: IHP MUST be able to tell, immediately after triggering an anticipated action on
  a HACS Scheduler entity, whether that action actually took effect on the climate entity, or
  was withheld because the scheduler's own conditions were not met. If the climate entity's
  resulting state cannot be read at all (unavailable/unknown), IHP MUST treat this as an
  unproven failure and MUST NOT fall back — only a positively confirmed mismatch triggers the
  fallback in FR-002.
- **FR-002**: When a triggered action is confirmed to have had no effect, IHP MUST retry with
  the next applicable scheduler among the remaining configured entities, re-anticipating that
  scheduler's own timeslot (its own target time and target temperature), rather than re-using
  the blocked scheduler's timeslot data.
- **FR-003**: IHP MUST NOT bypass a scheduler's configured conditions (no "force" actuation):
  the fallback is a change of *which* scheduler IHP anticipates, never a change to how that
  scheduler's own conditions are respected.
- **FR-004**: When every configured scheduler for this room is confirmed blocked within one
  recalculation cycle, IHP MUST stop attempting further triggers for that cycle and MUST
  surface this through both a WARNING log entry (identifying the scheduler by
  `friendly_name`) and a dashboard-visible sensor/attribute, so the household does not have
  to read logs to notice that anticipation could not be delivered.
- **FR-004a**: Scheduler exclusion is scoped to a single recalculation cycle only. IHP MUST
  NOT persist "blocked" state across cycles: the next periodic recalculation re-attempts the
  earliest scheduler first, and falls back again only if that attempt is itself confirmed
  blocked.
- **FR-005**: A room with a single configured scheduler, or only a native `schedule.*` entity,
  MUST behave exactly as it does today (see User Stories 2 and 3).
- **FR-006**: This feature stays within the existing domain/infrastructure boundaries: the
  domain layer keeps no dependency on `homeassistant.*`; detecting whether an action took
  effect, and selecting the next candidate scheduler, are implemented through the existing
  scheduler and climate-data interfaces (ABCs), not by reading any undocumented or internal
  HACS Scheduler data.
- **FR-007**: System MUST provide explicit typing on every public interface touched by this
  feature (reader, commander, climate-data interfaces and the use cases that orchestrate
  them).
- **FR-008**: System MUST log a WARNING when an action is confirmed blocked and an INFO entry
  for the fallback attempt itself (trying the next candidate) — the same level already used
  for a normal trigger, since attempting a candidate is routine activity, not an anomaly.
  Where the log is emitted by an infrastructure adapter that already has Home Assistant
  access (e.g. the existing "Triggering scheduler action" log), it names the scheduler by
  device `friendly_name` per the project's logging conventions; the application-layer
  use cases that detect the block and orchestrate the retry have no `homeassistant.*` access
  by design and log the scheduler entity id, consistent with every other log already in
  those classes.
- **FR-009**: Any new shared state introduced to track "blocked for this cycle" MUST be
  justified; a stateless recomputation per cycle is preferred unless state is required to
  avoid re-triggering the same blocked scheduler within a single recalculation pass.

### Workflow Requirements *(mandatory)*

- **WR-001**: The specification names `speckit.specify` as producer agent and `speckit.clarify`
  as critical reviewer agent (see front matter).
- **WR-002**: `speckit.checklist` reviews the plan, `speckit.analyze` reviews the generated
  tasks, and `speckit.review` reviews the implementation (see front matter).
- **WR-003**: The two clarification points raised during drafting (exclusion lifetime,
  visibility of a fully-blocked cycle) were resolved with the user before this spec was
  finalized; see the resolved Edge Cases above.

### Documentation Requirements *(mandatory)*

- **DR-001**: No user-facing documentation changes are anticipated — this is a correctness
  fix to behavior that was always intended to work this way; if `speckit.docs` later finds a
  contributor-facing note in `docs/architecture/` worth adding about the fallback behavior, it
  stays contributor-facing, not inside `docs/users/`.
- **DR-002**: `CHANGELOG.md` MUST gain an `[Unreleased]` entry describing the user-visible
  fix, per this project's branch-naming/PR convention for `fix/*` branches.
- **DR-003**: All new or updated artifacts (code, spec, docs) MUST be in English.

### Key Entities *(include if feature involves data)*

- **ScheduledTimeslot** (existing): a candidate upcoming timeslot — target time, target
  temperature, originating scheduler entity. This feature needs more than one candidate to be
  obtainable per recalculation, in ascending time order, with the ability to leave out
  specific scheduler entities already confirmed blocked.
- **Blocked scheduler (new, cycle-scoped)**: a scheduler entity confirmed, within the current
  recalculation cycle, to have had no effect when triggered. Not a new persisted entity —
  state needed only long enough to pick the next candidate and to stop once every candidate is
  exhausted (see Assumptions).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a household with two schedulers routed by a condition (e.g. vacation /
  non-vacation), the room reaches its scheduled target temperature at the intended time of
  whichever scheduler can actually act that day — not only after the blocked scheduler's own
  timeslot time has already passed.
- **SC-002**: Households with a single scheduler, or only a native schedule entity, observe
  zero behavior change.
- **SC-003**: When every configured scheduler is blocked on a given day, the household can
  tell, from the dashboard alone (no log inspection required), that anticipation could not be
  delivered that cycle, without IHP retrying forever or silently doing nothing.

## Assumptions

- The HACS Scheduler integration's `scheduler.run_action` call completes the conditions check
  and, when conditions hold, the nested climate service call, synchronously before returning
  control to the caller (confirmed by reading the integration's source) — so detecting "no
  effect" needs a state comparison right after the call, not a polling delay.
- "No effect" is detected by comparing the climate entity's resulting target temperature to
  the temperature IHP anticipated; this reuses the same preset/temperature resolution already
  used to build the `ScheduledTimeslot` in the first place, so the comparison is apples to
  apples.
- Multiple scheduler entities configured for the same room is an existing, supported
  configuration (already handled by today's "earliest across schedulers" selection); this
  feature changes only what happens when the selected one turns out to be blocked.
- Native `schedule.*` entities are out of scope for the fallback itself (they are never
  actuated by IHP), per [[ihp-computes-not-actuates]].
