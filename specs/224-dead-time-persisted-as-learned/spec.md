---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Only a Dead Time Learned From Heating Cycles Is Stored as Learned

**Feature Branch**: `fix/issue-224-dead-time-persisted-as-learned`
**Created**: 2026-10-31
**Status**: Draft
**Input**: GitHub issue #224 — "Configured default dead time is persisted as learned, and
rewritten on every restart"

## Context

IHP stores a **learned dead time** per device: the average delay between the start of heating
and the first temperature rise, measured on the heating cycles found in the history. The
Dead Time sensor shows it, and the anticipation uses it until the cycles are loaded in memory.
When nothing has been learned yet, both fall back to the **configured** dead time.

Two code paths write the learned dead time today:

1. The cycle extraction (`HeatingCycleLifecycleManager._persist_learned_dead_time`), after new
   cycles are stored or old ones are pruned. It averages **all** cached cycles (#185).
2. Every anticipation update (`HeatingApplication._async_update_locked`). It stores the dead
   time the anticipation has just used, whenever it differs from the last value it stored in
   memory.

The second path stores values that were never learned:

- With no cycles and nothing stored, the anticipation uses the configured dead time, which is
  then stored as learned.
- With auto-learning disabled, the anticipation always uses the configured dead time, which is
  stored as learned too.
- After `reset_learning`, the first update that runs before the extraction has relearned
  anything stores the configured dead time again: the cleared state does not stick.
- The value kept in memory starts empty, so the first update after each restart rewrites the
  stored value and fires a dead time update. On 0.7.0-rc1, every device logs
  `Learned dead time updated: …` at startup although nothing was recalculated.

Once the configured dead time is stored as learned, it takes precedence over the configured
value: a user who later changes the configured dead time still gets the old one.

## Clarifications

### Session 2026-10-31

- Q: Should the anticipation update stop writing the dead time, or only write values computed
  from cycles? → A: Stop writing. The extraction already stores the average of all cached
  cycles. The update computes its average on the cycles of the target time's window, a
  slightly different set: two writers would keep overwriting each other with close values,
  each time logging an update.
- Q: The update also fired the dead time event that refreshes the Dead Time sensor. Is the
  sensor still refreshed? → A: Yes. The sensor reads the stored value when it is added, and
  the extraction fires the event each time it stores a new value. A reset fires it too.
- Q: When a user turns auto-learning back on, the update used to store the cycles' average
  right away. Without it, nothing is learned until the next extraction finds new cycles,
  up to a day later. Is that acceptable? → A: No. The cache refresh, which runs at startup,
  after an options change and after a reset, also learns the dead time from the cached cycles
  when none were pruned. Cycles extracted while auto-learning was off are then learned from
  as soon as it is turned back on.
- Q: The refresh then recomputes the dead time on every restart. Does that bring back the
  rewrites at startup? → A: No. A learned dead time equal to the stored one is neither
  rewritten nor announced, whichever path computed it.
- Q: Are dead times already stored by mistake cleaned up? → A: They are replaced by the
  average of the cached cycles at the first cache refresh after the update, when the device
  has cycles with a measured dead time. Without such cycles, `reset_learning` clears them,
  and the reset now sticks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The configured dead time is never stored as learned (Priority: P1)

A user has no learned dead time yet (new device, no heating cycles, auto-learning disabled,
or just after a reset). IHP keeps recalculating the anticipation with the configured dead
time, and the stored learned dead time stays empty.

**Why this priority**: This is the defect of issue #224. A stored configured value hides
every later change of the configured dead time and makes `reset_learning` ineffective.

**Independent Test**: Run anticipation updates on a device whose storage holds no learned
dead time and check that nothing is stored.

**Acceptance Scenarios**:

1. **Given** no learned dead time is stored, **When** the anticipation is recalculated with
   the configured dead time, **Then** no learned dead time is stored.
2. **Given** auto-learning is disabled, **When** the anticipation is recalculated, **Then**
   no learned dead time is stored.
3. **Given** the learning data was just reset, **When** the anticipation is recalculated
   before the extraction has found any cycle, **Then** the learned dead time stays cleared.

### User Story 2 — A restart does not rewrite an unchanged dead time (Priority: P1)

A user restarts Home Assistant. The learned dead time of each device is kept as it was:
nothing is rewritten, nothing is logged as updated, no dead time update is announced.

**Why this priority**: The startup logs currently report updates that never happened, which
misleads anyone diagnosing the learning.

**Independent Test**: Run several anticipation updates and a cache refresh on a device whose
stored learned dead time matches its cached cycles, and check that nothing is written.

**Acceptance Scenarios**:

1. **Given** a learned dead time is stored, **When** the anticipation is recalculated after a
   restart, **Then** the stored value is not rewritten and no dead time update is announced.
2. **Given** a learned dead time equal to the average of the cached cycles, **When** the cache
   is refreshed, **Then** it is not rewritten and no dead time update is announced.

### User Story 3 — Turning auto-learning on learns from the cached cycles (Priority: P2)

A user who ran with auto-learning disabled turns it on. The dead time is learned from the
heating cycles already cached, without waiting for new ones.

**Why this priority**: The anticipation update used to cover this case; removing it must not
leave the Dead Time sensor on the configured value for up to a day.

**Independent Test**: Refresh the cache of a device with auto-learning enabled, cached cycles
and no learned dead time, without pruning anything.

**Acceptance Scenarios**:

1. **Given** cached cycles with a measured dead time and no learned dead time stored, **When**
   the cache is refreshed and no cycle is pruned, **Then** the average of the cached cycles is
   stored and announced.

### Edge Cases

- **Configured dead time of 0 (the default)**: it is not stored either; the stored value stays
  empty instead of 0.
- **Cycles without any measured dead time**: nothing is learned and nothing is stored.
- **Auto-learning disabled at refresh time**: nothing is learned, as during an extraction.
- **Cache unreadable during the refresh**: the error is logged and nothing is learned; the
  stored value is kept.
- **Anticipation using a slightly different average**: when the cycles are loaded, the
  anticipation averages the cycles of the target time's window; the sensor shows the stored
  average of all cached cycles. Both come from the same cycles (unchanged behavior).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The anticipation update MUST NOT store the learned dead time nor announce a
  dead time update.
- **FR-002**: The learned dead time MUST only be stored from the average dead time of the
  cached heating cycles, when auto-learning is enabled.
- **FR-003**: A learned dead time equal to the stored value MUST NOT be rewritten, logged as
  updated or announced.
- **FR-004**: The cache refresh MUST learn the dead time from the cached cycles when no cycle
  is pruned, as it already does after pruning.
- **FR-005**: `reset_learning` MUST leave the learned dead time cleared until cycles with a
  measured dead time are learned again.

### Key Entities

- **Learned dead time**: the stored average dead time of the cached heating cycles. Empty
  until such cycles exist.
- **Configured dead time**: the value from the options, used whenever no learned dead time
  is stored or auto-learning is disabled. Never stored as learned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 learned dead time writes from the anticipation update.
- **SC-002**: 0 `Learned dead time updated` log lines at a restart where no new cycle is
  learned (today: one per device).
- **SC-003**: After `reset_learning`, the stored learned dead time stays empty until the
  extraction learns new cycles.

## Assumptions

- The average of the same cached cycles is deterministic, so an unchanged cache yields a value
  equal to the stored one.
- The Dead Time sensor reads the stored value when added and on every dead time update event
  (unchanged).

## Known Limitations

- A `reset_learning` running at the very moment a cache refresh learns the dead time can still
  see the pre-reset value written back. This race already exists for the LHS and the pruning
  path and is tracked by #225.
