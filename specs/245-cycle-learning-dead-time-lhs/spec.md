---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Cycle's Dead Time and Heating Slope Are Measured Where Heating Really Starts

**Feature Branch**: `fix/issue-245-cycle-learning-dead-time-lhs`
**Created**: 2026-10-31
**Status**: Draft
**Input**: GitHub issue #245 — "Cycle learning: dead-time threshold float error, LHS not measured
from dead-time end, rejected cycles feed the dead time"

## Context

For each heating cycle found in the history, IHP measures two values:

- The **dead time**: the time from heating start until the indoor temperature reaches
  `start_temp + 0.2 °C`. A fall of the temperature after heating starts, and the time spent
  climbing back, is intentionally part of it; the 0.2 °C threshold protects against sensor
  noise. This definition is kept.
- The **heating slope** (LHS): how fast the room heats once the dead time is over.

The learned dead time is the average dead time of the cached cycles. The global and
contextual LHS average the slopes of the cycles accepted by the shared realistic-cycle rule
(`filter_realistic_cycles`, #223). The anticipation is `dead_time + Δ / LHS`.

Three defects bias both learned values:

1. **Float error on the threshold** — `current_temp - start_temp >= 0.2` misses a rise of
   exactly 0.2 °C for most values: `18.2 - 18.0` is `0.19999999999999929` in floating point.
   With a 0.1 °C sensor the effective threshold becomes 0.3 °C, adding `0.1 / slope` to every
   dead time (6 min at 1 °C/h, 12 min at 0.5 °C/h).
2. **Slope not measured from the end of the dead time** — `HeatingCycle.avg_heating_slope`
   divides by the duration after the dead time but uses `end_temp - start_temp` as numerator.
   The rise during the dead time (at least 0.2 °C by definition) is counted in a window that
   excludes it, so the slope is overestimated: 1.27 °C/h for a room heating at 1.0 °C/h.
3. **Rejected cycles feed the dead time** — `DeadTimeCalculationService` averages every cycle
   with a positive dead time, including cycles the LHS rejects. A typical one: the temperature
   falls, climbs back and reaches the threshold at the last reading. Its dead time is the whole
   cycle, its slope is 0, it is excluded from the LHS, but its full duration goes into the
   learned dead time.

With cycle splitting enabled, a fourth defect (#218, point 1) makes the corrected slope
inconsistent: sub-cycle temperatures are interpolated linearly from the cycle start, which
already spreads the dead time over the whole cycle, and the first sub-cycle then removes it a
second time. Its slope is inflated, or 0 when the dead time is longer than the sub-cycle.

## Clarifications

### Session 2026-10-31

- Q: With the dead time ending at `start_temp + 0.2 °C` and the slope measured from there, the
  first 0.2 °C is covered by both the dead time and `Δ / LHS`: the anticipation gets about
  `0.2 / LHS` longer (≈ 12 min at 1 °C/h). Accept it or compensate for it? → A: Accept it. The
  prediction formula is unchanged. The formula takes `Δ` from the temperature at the time of
  the calculation, while the room keeps cooling until preheating starts, so the real gap is
  usually larger; a late start costs comfort, an early one only a few minutes of heating.
  Keeping the formula also keeps the meaning of the Initial Dead Time setting ("delay before
  the temperature starts rising"). A compensation can be reconsidered separately, from real
  arrival data.
- Q: Cycles already in the cache have no temperature at the end of their dead time. Fall back
  or re-extract them? → A: Fall back to `start_temp + 0.2 °C`, the temperature at the end of
  the dead time by definition (exact for a 0.1 °C sensor). Re-extracting would load the
  Recorder for every device at upgrade, and history older than the Recorder retention cannot
  be re-read. `reset_learning` re-extracts the cycles still in the Recorder history for users
  who want their dead times measured again with the corrected threshold.
- Q: How do split sub-cycles stay consistent with the new slope (#218, point 1)? → A: The
  heating phase of the cycle, from the end of the dead time to the cycle end, is split into
  windows of the split duration, with temperatures interpolated from the temperature at the end
  of the dead time. The first sub-cycle starts at the cycle start and covers the dead time plus
  its first window; it keeps the dead time and the temperature at its end. Every sub-cycle then
  has the slope of the heating phase, and the dead time is learned only if that slope is
  realistic, as for an unsplit cycle. A cycle whose heating phase is not longer than the split
  duration is not split. Without a dead time, splitting is unchanged.
- Q: Does #218 close with this fix? → A: No. Its point 2 (removing the dead
  `update_cycles_for_window`) is out of scope and stays tracked there.
- Q: When do the stored values reflect the corrections after an upgrade? → A: The learned dead
  time is recalculated at the first cache refresh (startup), now excluding rejected cycles. The
  stored global and contextual LHS are recalculated from all cached cycles at the next
  extraction or pruning, within 24 hours, as for any new cycle.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A rise of exactly 0.2 °C ends the dead time (Priority: P1)

A room starts heating at 18.0 °C. The first reading 0.2 °C higher ends the dead time, whatever
the temperature values.

**Why this priority**: Every dead time measured with a 0.1 °C sensor is one reading too long
today, and it feeds both the dead time and, through it, the slope.

**Independent Test**: Extract a cycle whose temperature stays flat 30 minutes then rises
0.1 °C every 6 minutes, and check the dead time.

**Acceptance Scenarios**:

1. **Given** a cycle starting at 18.0 °C, flat for 30 minutes, then rising 1.0 °C per hour
   with a reading every 6 minutes, **When** the cycle is extracted, **Then** its dead time is
   42 minutes (the 18.2 °C reading), not 48.
2. **Given** temperatures such as 19.1 → 19.3 or 20.3 → 20.5, **When** the dead time is
   measured, **Then** the 0.2 °C rise ends it.
3. **Given** a rise of 0.19 °C, **When** the dead time is measured, **Then** it does not end it.

### User Story 2 — The heating slope is measured from the end of the dead time (Priority: P1)

The heating slope of a cycle is the temperature gained after the dead time divided by the time
after the dead time.

**Why this priority**: The overestimated slope shortens every anticipation computed from it.

**Independent Test**: Extract the cycles of User Story 1 and of a cycle whose temperature
first falls, and check their slopes.

**Acceptance Scenarios**:

1. **Given** the cycle of User Story 1 (18.0 → 19.8 °C, dead time ending at 18.2 °C),
   **When** its slope is computed, **Then** it is 1.0 °C/h, not 1.2.
2. **Given** a cycle starting at 18.0 °C that falls 0.4 °C in 24 minutes, then rises
   1.0 °C per hour, **When** the cycle is extracted, **Then** its dead time is 60 minutes and
   its slope 1.0 °C/h.
3. **Given** a cycle without a dead time, **When** its slope is computed, **Then** it is
   measured from the cycle start, as before.
4. **Given** a cycle cached before this fix, with a dead time but no temperature at its end,
   **When** its slope is computed, **Then** it is measured from `start_temp + 0.2 °C`.

### User Story 3 — Only cycles kept for the slope teach the dead time (Priority: P1)

A cycle rejected from the heating slope is not used to learn the dead time either.

**Why this priority**: One rejected cycle can add its whole duration to the learned dead time.

**Independent Test**: Learn the dead time from a normal cycle and from a cycle that falls,
climbs back and stops when it reaches the threshold.

**Acceptance Scenarios**:

1. **Given** the cycle of User Story 1 (dead time 42 minutes) and a cycle from 19.5 °C that
   falls to 19.2 °C and is switched off when it climbs back to 19.7 °C 48 minutes later,
   **When** the dead time is learned, **Then** it is 42 minutes, not 45.
2. **Given** only rejected cycles, **When** the dead time is learned, **Then** nothing is
   learned and the configured or stored dead time stays in use.

### User Story 4 — Split cycles keep the slope of the heating phase (Priority: P2)

A user with cycle splitting enabled gets sub-cycles whose slopes match how fast the room heats,
and keeps learning the dead time.

**Why this priority**: Splitting is disabled by default, but with it enabled the corrected
slope would otherwise reject the first sub-cycle, and with it the dead time, as soon as the
dead time is longer than a sub-cycle.

**Independent Test**: Extract the cycle of User Story 1 with a 30-minute split.

**Acceptance Scenarios**:

1. **Given** the cycle of User Story 1 and a 30-minute split, **When** it is extracted,
   **Then** every sub-cycle has a slope of 1.0 °C/h.
2. **Given** the same extraction, **Then** only the first sub-cycle carries the 42-minute dead
   time, and it starts at the cycle start.
3. **Given** a cycle whose heating phase is not longer than the split duration, **When** it is
   extracted, **Then** it is not split.

### Edge Cases

- **Dead time ending at the last reading of the cycle**: the heating phase is empty, the slope
  is 0 (minimum effective duration guard), the cycle is rejected and its dead time not learned.
- **Dead time above 180 minutes**: still discarded as a data artifact (no dead time, slope
  measured from the cycle start).
- **Cycle without any rise of 0.2 °C**: no dead time, slope from the cycle start (unchanged).
- **Sensor with a 0.05 °C or finer resolution**: the threshold stays 0.2 °C; only the float
  error is absorbed, not real differences.
- **Anticipation using the cycles of the target time's window**: their dead time average
  applies the same rule as the stored one.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A temperature rise equal to the dead time threshold MUST end the dead time,
  regardless of floating-point representation.
- **FR-002**: Each cycle MUST record the indoor temperature at the end of its dead time, and
  the cycle cache MUST persist it.
- **FR-003**: A cycle's heating slope MUST be `(end_temp − temperature at the end of the dead
  time) / (end_time − end of the dead time)`. Without a dead time it MUST stay
  `(end_temp − start_temp) / (end_time − start_time)`.
- **FR-004**: For a cycle with a dead time but no recorded temperature at its end, the slope
  MUST use `start_temp + 0.2 °C`.
- **FR-005**: The dead time MUST be learned only from cycles accepted by the realistic-cycle
  rule shared with the LHS, evaluated with the corrected slope. This applies to the stored
  learned dead time and to the dead time averaged by the anticipation.
- **FR-006**: With splitting enabled, the heating phase MUST be split from the end of the dead
  time, the first sub-cycle MUST cover the dead time and keep it with the temperature at its
  end, and the other sub-cycles MUST have no dead time.
- **FR-007**: The anticipation formula MUST stay `dead_time + Δ / LHS`.

### Key Entities

- **Heating cycle**: gains the temperature at the end of its dead time (optional; absent from
  cycles cached before this fix and from cycles without a dead time).
- **Dead time threshold**: the 0.2 °C rise that ends the dead time, now a shared domain
  constant used by the extraction and by the slope fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a 0.1 °C sensor, the measured dead time ends at the first reading 0.2 °C above
  the start temperature (today: often 0.3 °C).
- **SC-002**: On the cycles of the issue's reproduction, the slope found equals the actual rise
  rate after the dead time (today: up to 27 % higher).
- **SC-003**: 0 rejected cycles in the learned dead time.

## Assumptions

- Indoor temperatures are reported with at least 0.1 °C resolution, so a reading of exactly
  `start_temp + 0.2 °C` exists when the room heats.
- The cycles' heating phase is close to linear, as the slope model already assumes.

## Known Limitations

- Dead times of cycles already cached were measured with the float error and stay one reading
  too long until those cycles leave the retention window, unless `reset_learning` re-extracts
  them.
- The anticipation is about `0.2 / LHS` longer than the model's exact value (see
  Clarifications), deliberately.
