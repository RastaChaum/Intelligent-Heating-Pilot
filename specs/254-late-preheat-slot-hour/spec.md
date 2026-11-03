---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Late Preheat Is Learned by the Slot It Was Heating For

**Feature Branch**: `fix/issue-254-late-preheat-slot-hour`
**Created**: 2026-11-03
**Status**: Draft
**Input**: GitHub issue #254 — "Contextual LHS: a late preheat cycle is filed under a later hour,
so its slot never learns it is late"

## Context

Since #214, a cycle is filed under the hour nearest to its end (`contextual_hour(end_time)`), and
a slot reads the hour nearest to its time (`contextual_hour(target_time)`). This works for cycles
that reach the target up to half an hour around the slot. A preheat that is **late** by more
than that is filed under a later hour, and the slot that produced it never sees it.

A slot therefore only learns from the preheats that reached the target on time, which are the
fast ones. The bias reinforces itself: the later the preheats of a slot, the less the slot learns
about them, and its contextual LHS stays optimistic.

### Observed (2026-11-01, IHP v0.7.1-rc1)

Living room, underfloor heating (VTherm `over_switch`, TPI). Weekend slot: comfort 20 °C at 08:45,
which reads hour 09.

- The preheat started at 06:20 at 18.9 °C with the contextual LHS of hour 09: 0.87 °C/h. The
  global LHS was 0.53 °C/h.
- The room reached 19.8 °C (cycle end, `target - 0.2`) at 09:56, 82 min late.
- The cycle is filed under hour 10. Hour 09 never learns from it. Same on 2026-10-31.

### What the Recorder holds about the slot

Cycles are rebuilt from the Recorder history of the thermostat, which holds no trace of the slot a
cycle was aimed at. IHP's own **Next Schedule Time** sensor does: its state is the time of the
next slot IHP aims at, and its `next_target_temperature` attribute the target of that slot. The
sensor is recorded by the Recorder like any other entity, so its history tells, for every past
day IHP ran on, which slots came due and when.

## Clarifications

### Session 2026-11-03

- Q: Where does the slot of a cycle extracted from the Recorder come from? (a) IHP persists the
  target time of each preheat it triggers, (b) the scheduler timeslots read today, (c) the moment
  a slot came due during the cycle? → A: (c), read from the history of IHP's Next Schedule Time
  sensor. (a) needs a new store and knows nothing of the cycles already in the history. (b) reads
  the schedule as it is today, not as it was: slots edited since, slots relative to sunrise, and
  slots skipped because their conditions were not met (#64) would be misplaced. The Next Schedule
  Time sensor records the slot IHP actually aimed at, including the fallback scheduler, and its
  history covers every day IHP ran on.
- Q: Which cycles are tied to a slot? → A: A cycle during which a slot came due: the slot time is
  after the cycle start and not after its end, and the slot target equals the cycle target. The
  room was still heating toward the slot's target when the slot came due, so the cycle is the
  late preheat of that slot. If several slots came due during a cycle, the first one is used.
  A slot with another target (an eco slot coming due during a comfort cycle) is not the slot the
  cycle heated for.
- Q: What about cycles that end before their slot? → A: Unchanged: no slot came due during them,
  so they keep the nearest-hour rule of #214, which already files a cycle ending up to half an
  hour before a whole-hour slot under that slot. The history only tells reliably which slot came
  due during a cycle; tying a cycle that ended earlier to the next slot would also tie unrelated
  cycles, such as a manual heat-up in the afternoon to an evening slot of the same target.
- Q: What happens to the cycles already in the cache? → A: They carry no slot and keep the
  nearest-hour rule, as they did before. Re-extracting the whole history on upgrade would be
  costly; cached cycles are replaced as the retention window moves on, or right away with
  `reset_learning`, which re-extracts the history.
- Q: Split sub-cycles (`cycle_split_duration_minutes > 0`)? → A: The slot is found on the whole
  cycle, and every sub-cycle carries it, like the disturbance status (#255). Since #245 every
  sub-cycle has the slope of the whole heating phase, so all of them belong to the slot.
- Q: What if the Next Schedule Time sensor has no history (excluded from the Recorder, disabled,
  IHP installed after the cycle, history read failure)? → A: Cycles get no slot and keep the
  nearest-hour rule. The slot history is optional, like the outdoor temperature: a failed read
  must not fail the extraction of the period.
- Q: Does the read side change? → A: No. A slot still reads the contextual hour of its time
  (#214), which is the hour a tied cycle is filed under.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A late preheat counts for the slot it heated for (Priority: P1)

A user has a weekend slot at 08:45 (comfort 20 °C). The preheat starts at 06:20 and reaches the
target at 09:56. Its slope is learned for the 08:45 slot, which reads hour 09.

**Why this priority**: This is the defect of issue #254. Without it a slot never learns that its
preheats are late, and keeps starting them too late.

**Independent Test**: Extract a cycle from 06:20 to 09:56 from a history in which a 20 °C slot
came due at 08:45, learn the contextual slopes, then read the slope of an 08:45 slot.

**Acceptance Scenarios**:

1. **Given** a preheat from 06:20 to 09:56 during which a 20 °C slot came due at 08:45, **When**
   the slope of an 08:45 slot is read, **Then** it is the slope of that preheat.
2. **Given** the same preheat, **When** the slope of a 10:00 slot is read, **Then** it is not the
   slope of that preheat.

### User Story 2 — Cycles not tied to a slot keep the nearest hour (Priority: P1)

A cycle during which no slot of its target came due keeps the hour nearest to its end: a preheat
that lands before its slot, a manual heat-up, a cycle whose slot history is unknown.

**Why this priority**: The fix must not move the cycles #214 already files correctly.

**Acceptance Scenarios**:

1. **Given** a cycle from 05:40 to 06:58 and a slot that came due at 07:00, **When** the slopes
   are learned, **Then** the cycle counts for hour 07, as before.
2. **Given** a cycle from 06:00 to 09:56 during which an 18 °C slot came due at 08:45 while the
   cycle heated toward 20 °C, **When** the slopes are learned, **Then** the cycle counts for hour
   10.
3. **Given** a cycle from 06:20 to 09:56 and no slot history, **When** the slopes are learned,
   **Then** the cycle counts for hour 10.

### User Story 3 — Every sub-cycle of a late preheat counts for its slot (Priority: P2)

With cycle splitting enabled, every sub-cycle of a late preheat carries the slot of the preheat.

**Acceptance Scenarios**:

1. **Given** splitting every 60 min and a preheat from 06:20 to 09:56 during which a 20 °C slot
   came due at 08:45, **When** cycles are extracted, **Then** every sub-cycle carries the 08:45
   slot.

### User Story 4 — The slot survives a restart (Priority: P2)

The slot of a cycle is stored with it in the cycle cache, so the contextual LHS recalculated after
a restart files the cycle under the same hour. Cycles cached before the fix load without a slot.

**Acceptance Scenarios**:

1. **Given** a cached cycle tied to an 08:45 slot, **When** the cache is reloaded, **Then** the
   cycle still carries the 08:45 slot.
2. **Given** a cycle cached before the fix, **When** the cache is reloaded, **Then** it carries no
   slot.

### Edge Cases

- **Slot exactly at the cycle end**: tied; it is also the nearest hour, so nothing changes.
- **Slot exactly at the cycle start**: not tied; the cycle started when the slot was applied,
  it did not preheat for it.
- **Several slots of the same target during one long cycle**: the first one is used.
- **Next Schedule Time state `unknown` or `unavailable`** (restart, scheduler off): skipped.
- **Slot without a known target**: skipped; it cannot be matched to the cycle.
- **Timezones**: slot and cycle times are compared as instants; the contextual hour of the slot
  is read on the local clock, like the end time of the other cycles.
- **Slot recorded once, several times**: the sensor may record the same slot again after a
  restart; it is one slot.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cycle extraction MUST read, for each period, the slots that came due: the distinct
  states of IHP's Next Schedule Time sensor, with the target of each.
- **FR-002**: A cycle MUST be tied to the first slot that came due after its start and not after
  its end, whose target equals the cycle target. Otherwise it has no slot.
- **FR-003**: Every sub-cycle of a split cycle MUST carry the slot of its cycle.
- **FR-004**: The contextual LHS MUST file a cycle tied to a slot under the contextual hour of the
  slot, and any other cycle under the contextual hour of its end (#214).
- **FR-005**: The cycle cache MUST persist the slot of each cycle; cycles cached before the fix
  MUST load without one.
- **FR-006**: A missing, unreadable or empty slot history MUST NOT fail the extraction of a
  period; its cycles get no slot.
- **FR-007**: The slot history MUST be read through a domain interface; the domain MUST NOT know
  the sensor or the Recorder.

### Key Entities

- **Scheduled slot**: a moment at which a slot of the schedule came due, with its target
  temperature.
- **Heating cycle**: gains the optional time of the slot it was heating for.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A preheat that reaches the target after its slot, however late, is learned for that
  slot (today: only up to 30 min late for a whole-hour slot, 15 min for an `h:45` slot).
- **SC-002**: The filing of cycles during which no slot of their target came due is unchanged.
- **SC-003**: Extraction still succeeds when the Next Schedule Time sensor has no history.

## Assumptions

- The Next Schedule Time sensor is recorded by default; its entity is found through the entity
  registry by its unique id, so a renamed entity is still found.
- A cycle heats toward the target it had when it started (unchanged).

## Known Limitations

- **Early preheats more than half an hour before their slot** keep the nearest-hour rule and are
  filed under an earlier hour (#214).
- **Cached cycles** keep the nearest-hour rule until they leave the retention window or
  `reset_learning` is called.
- **Slots of the schedule that IHP did not aim at** (another scheduler chosen at that time) are not
  in the history and cannot be tied.

## Out of Scope

- Brief interruptions that fragment a preheat into several cycles (#260): only the fragment
  during which the slot came due is tied to it.
