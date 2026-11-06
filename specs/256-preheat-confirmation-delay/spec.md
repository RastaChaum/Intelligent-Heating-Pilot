---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Preheat Is Confirmed Once the Thermostat Has Applied It

**Feature Branch**: `fix/issue-256-preheat-confirmation-delay`
**Created**: 2026-11-03
**Status**: Draft
**Input**: GitHub issue #256 — "Preheat confirmation reads the VTherm before run_action takes
effect, so the scheduler is wrongly reported blocked"

## Context

Since #64, `ControlPreheatingUseCase.start_preheating` checks that a triggered scheduler action
took effect: it calls `run_action`, then reads the VTherm target temperature. A target that does
not match the slot's temperature means the scheduler's own conditions withheld the action: the
preheat is not marked active and the orchestrator retries with the next candidate scheduler.

The `scheduler.run_action` service call is `blocking=True`, but scheduler-component returns before
the climate entity has applied the action. The check reads the old setpoint and reports a scheduler
that did act as blocked.

### What the logs show (2026-11-01, IHP v0.7.1-rc1)

| Time | Event |
|---|---|
| 06:20:03.933 | VTherm in preset eco, 18 °C. The anticipated start is past → immediate trigger |
| 06:20:03.937 | IHP sensor: `blocked_schedulers: [<weekend scheduler>]`, next slot = the weekday scheduler's |
| 06:20:03.945 | VTherm switches to preset comfort, 20 °C: the action did apply, 8 ms after the check |
| 07:20:05 | Next recalculation: `run_action` sent again, now confirmed |

For an hour IHP believed no preheat was active. With another scheduler next in line, it would have
triggered that scheduler's slot as well.

## Clarifications

### Session 2026-11-03

- Q: Wait for the VTherm state change, or sleep for a fixed time? → A: Wait for the VTherm's state
  changes. After `run_action`, IHP reads the target; while it does not match, IHP waits for the next
  state change of the VTherm and reads it again. A matching target confirms the action as soon as
  it is applied, with no fixed delay.
- Q: How long does IHP wait? → A: 10 seconds at most (`ACTION_EFFECT_TIMEOUT_SECONDS`), not a
  user setting. The observed delay is 8 ms; 10 s leaves a wide margin for a busy Home Assistant
  while keeping the fallback to the next scheduler prompt when one is really blocked.
- Q: The wait ends with no matching target: blocked or unknown? → A: Blocked, as a mismatch is
  today. The thermostat had its chance to apply the action and did not. An unreadable target
  (VTherm unavailable) is still treated as success, as decided for #64.
- Q: What if the target already matches right after `run_action`? → A: Confirmed at once, no wait
  (today's behavior).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A scheduler that acts is never reported blocked (Priority: P1)

A household has a weekday and a weekend scheduler. The weekend scheduler's slot is next and its
conditions hold. When IHP triggers it, the thermostat switches to comfort a few milliseconds after
`run_action` returns.

**Why this priority**: This is the defect of #256. A wrong "blocked" leaves the preheat untracked
for an hour and can trigger another scheduler's slot.

**Independent Test**: Simulate a thermostat that applies the action only after `run_action` has
returned, trigger the preheat, and check that it is confirmed, with no scheduler reported blocked
and no other scheduler triggered.

**Acceptance Scenarios**:

1. **Given** a thermostat that applies a triggered action a moment after `run_action` returns,
   **When** IHP triggers a scheduler whose conditions hold, **Then** the preheat is active for that
   scheduler, the room's target becomes the slot's temperature and no scheduler is reported
   blocked.
2. **Given** the same thermostat and a second scheduler next in line, **When** IHP triggers the
   first scheduler and its conditions hold, **Then** the second scheduler is never triggered.

### User Story 2 — A really blocked scheduler still falls back (Priority: P1)

**Why this priority**: The fallback of #64 must keep working once IHP waits for the thermostat.

**Acceptance Scenarios**:

1. **Given** a thermostat that applies a triggered action a moment after `run_action` returns and
   a first scheduler blocked by its own conditions, **When** IHP triggers it, **Then** after the
   wait it is reported blocked and the next scheduler takes over within the same recalculation.

### Edge Cases

- The VTherm changes state for another reason during the wait (indoor temperature update): IHP
  reads the target again and keeps waiting until the deadline.
- The VTherm applies the preset first and the temperature in a later state update: the first
  change does not match, the second one confirms.
- The VTherm becomes unavailable during the wait: the target is unreadable → success (#64).
- Native `schedule.*` entities: no action is triggered, nothing is verified or awaited.
- No climate reader configured: no verification, as today.

## Requirements *(mandatory)*

- **FR-001**: After `run_action`, a target that already matches confirms the preheat with no wait.
- **FR-002**: Otherwise IHP waits for the VTherm's state changes, reading the target after each one,
  until it matches or `ACTION_EFFECT_TIMEOUT_SECONDS` (10 s) have elapsed since the first read.
- **FR-003**: A target that still does not match at the deadline reports the scheduler blocked, as
  a mismatch does today; an unreadable target is a success.
- **FR-004**: The wait uses the VTherm's state change events (no polling, no fixed sleep). The
  listener is always removed when the wait ends.
- **FR-005**: The domain contract `IClimateDataReader` gains the wait; the HA adapter only
  translates the state change events. The matching rule stays in the application layer.

## Out of Scope

- A trigger made while the VTherm itself holds a lower target (window open, load shedding): the
  target does not match within the wait and the scheduler is reported blocked, as today.
- Serializing the event-driven and the periodic recalculations (pre-existing; the wait only lasts
  when a scheduler is really blocked).

## Success Criteria

- **SC-001**: The BDD scenario with a delayed thermostat confirms the preheat with no scheduler
  blocked; it fails on the code before the fix.
- **SC-002**: The #64 fallback scenarios still pass.
