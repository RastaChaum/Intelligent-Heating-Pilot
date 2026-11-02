---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Slow Cycles Are Learned, Disturbed Cycles Are Recognised by the Thermostat's Own Signals

**Feature Branch**: `fix/issue-255-slow-cycle-dead-time-cap`
**Created**: 2026-11-02
**Status**: Draft
**Input**: GitHub issue #255 — "Cycle learning drops slow but genuine cycles (dead time > 180 min,
slope < 0.2 °C/h), biasing dead time and LHS"

## Context

IHP learns two values from the heating cycles found in the history: the **dead time** (from
heating start until the room has gained 0.2 °C) and the **heating slope** (LHS, measured after
the dead time since #245). Two thresholds remove slow cycles from both:

1. **Dead time cap** — `HeatingCycleService._calculate_dead_time_cycle` treats a dead time above
   180 minutes as a data artifact and drops it. The slope of that cycle is then measured from
   the cycle start over the whole cycle, dead time included.
2. **Slope floor** — `is_realistic_learning_cycle` rejects a cycle whose slope is below
   `MINIMUM_REALISTIC_LHS` (0.2 °C/h). Since #245 the same rule removes it from the dead time.

The floor was meant to discard cycles disturbed by safety mode or load shedding (#223). It cannot
tell them from a heating system that is genuinely slow, such as underfloor heating at partial TPI
power. The same 0.2 °C/h floor also guards the averaged values: a global or contextual LHS below
it, stored or about to be used, is replaced by the 2.0 °C/h default.

### What the history shows (replay of the rc1 extraction, 2026-10-23 → 2026-11-02, 8 VTherms)

| Room | Day | With the 180 min cap | Without the cap |
|---|---|---|---|
| Living room (floor heating) | 2026-10-30 | dead time dropped, slope 0.22 °C/h over the whole cycle | dead time 202 min, slope 1.11 °C/h |
| Living room | 2026-10-31 | dead time dropped, slope 0.09 °C/h → rejected | dead time 243 min, slope 0.65 °C/h |
| Bedroom "chambre" | 2026-11-01 | dead time dropped, slope 0.09 °C/h → rejected | dead time 187 min, slope 0.40 °C/h |

The bedroom has learned nothing (its sensors show the 2.0 °C/h default and a 0 min dead time).

The same replay shows which disturbance signals the Recorder keeps. VTherm marks its
`safety_manager`, `power_manager`, `window_manager` and `specific_states` attributes as
unrecorded (checked on VTherm 10.6.3 and on the live Recorder). What remains in the history is
`preset_mode`, `hvac_mode`, the target `temperature`, `hvac_action` and `power_percent`:

- **Load shedding**: the preset becomes `power` and the target drops to the power temperature.
  The target drop already ends the IHP cycle.
- **Safety mode**: the preset becomes `safety` and the target is kept. The cycle goes on while
  the heater runs at the safety power (0 % by default), so the room stays flat. This is the
  #223 disturbance.
- **Window**: the target drops to the window action temperature, or `hvac_mode` turns `off`.
  Either ends the cycle.

## Clarifications

### Session 2026-11-02

- Q: Which recorded signals mark a cycle as disturbed? → A: The VTherm presets `power` (load
  shedding) and `safety` (safety mode), read from the recorded `preset_mode` of the heating state
  history. These presets are set by VTherm itself and never chosen by a user. Windows and
  `hvac_mode` off need no flag: they already end the cycle.
- Q: Keep a speed floor on the heating slope? → A: No. A cycle is excluded because of an explicit
  signal, not because of its speed: any strictly positive heating slope is learned. The trade-off
  was accepted knowingly: disturbances that leave no recorded signal are learned too. On
  2026-11-02, two radiator rooms heated at 0.08–0.09 °C/h with 43–87 % power after a load
  shedding, with no signal in the history. A floor would have rejected them, but it also rejects
  genuine phases at 0.13–0.19 °C/h (bedroom on 2026-10-28, upstairs bathroom on 2026-10-31 and
  2026-11-01), and only a single 0.1 °C sensor step separates the two groups.
- Q: A cycle whose temperature never rises 0.2 °C before it ends: dead time equal to its duration,
  or unknown? → A: Unknown, and the cycle is not learned at all. The cycle duration is only a
  lower bound: learning it would shorten the learned dead time, the bias this issue fixes. Such a
  cycle has no heating phase, and its slope measured from the start (typically one 0.1 °C step
  over the cycle) would be learned as a near-zero LHS now that there is no speed floor. Today
  these short cycles enter the LHS (e.g. 1.20 °C/h for a 5-minute cycle gaining 0.1 °C).
- Q: What replaces the 180-minute cap: `MAX_ANTICIPATION_TIME` (360 min) or nothing? → A:
  Nothing. Since #185 the dead time search stops at the cycle end, and the cycle is bounded by the
  Maximum Cycle Duration setting (300 min by default). Any cap below that drops precisely the
  slowest cycles. If a user raises the setting above 360 min, a dead time longer than the longest
  anticipation saturates it at its maximum, which is the right direction for a slow room.
- Q: The averaged values (global LHS, contextual LHS, stored LHS, LHS used by the anticipation)
  are still checked against 0.2 °C/h. Keep that? → A: No, a learned slope is valid when strictly
  positive. Otherwise a room whose cycles all heat at 0.1–0.19 °C/h would learn them and still
  fall back to the 2.0 °C/h default, i.e. a far too short anticipation.
- Q: Cycles already in the cache carry no disturbance information. Apply the new rule to them? →
  A: No. A cycle cached before this fix keeps the former rule (slope ≥ 0.2 °C/h, no requirement
  on the dead time). Accepting any positive slope from cycles whose disturbance is unknown would
  bring back the #223 safety-mode cycles still in the 30-day retention. `reset_learning`
  re-extracts the cycles still in the Recorder history with the new rule. The others leave the
  cache as they age out.
- Q: A global or contextual LHS below 0.2 °C/h stored by an earlier version (from cycles disturbed
  before #184 / #223) becomes usable. Remove it on read, as today? → A: No. It cannot be told
  apart from a slow slope learned after this fix. The stored LHS is recalculated from the cached
  cycles at the next extraction or daily refresh. Until then such a value makes preheating start
  too early, never too late. Only a value that is not positive is still removed on read.
- Q: A brief load shedding or window opening splits a preheat into fragments, and the dead time of
  the last fragment is measured from its own start (living room 2026-11-02: 73 min learned
  instead of ≈ 142 min). In scope? → A: No. It is tracked in #260.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A slow underfloor preheat is learned with its real dead time (Priority: P1)

A room with underfloor heating takes four hours before its temperature starts rising. IHP learns
that dead time and the heating slope that follows it, so the next preheat starts early enough.

**Why this priority**: The slowest preheats are the ones that teach IHP to start earlier. Today
they are dropped, and the learned dead time only describes the fast mornings (85.8 min learned
in the living room against 160–243 min observed).

**Independent Test**: Extract a cycle whose temperature stays flat for 240 minutes and then rises,
and learn the dead time and LHS from it.

**Acceptance Scenarios**:

1. **Given** a cycle starting at 05:00 at 19.4 °C, flat until a 19.6 °C reading at 09:00 and
   ending at 19.8 °C at 09:20, **When** the cycle is extracted, **Then** its dead time is
   240 minutes and its heating slope 0.6 °C/h.
2. **Given** that cycle, **When** the dead time and the global LHS are learned, **Then** both
   include it.
3. **Given** a cycle whose dead time ends at its last reading, **When** it is learned, **Then**
   it is excluded, as before: its heating phase is shorter than the minimum effective duration
   and its slope is 0.

### User Story 2 — A cycle disturbed by safety mode or load shedding is never learned (Priority: P1)

A cycle during which the thermostat reported safety mode or load shedding teaches neither the
dead time nor the heating slope, however fast or slow it heated.

**Why this priority**: Without a speed floor, this signal is what keeps the #223 disturbances
out of the learned values.

**Independent Test**: Extract cycles whose heating state history contains the `safety` or the
`power` preset, and learn from them.

**Acceptance Scenarios**:

1. **Given** a cycle during which the thermostat preset is `safety` for 30 minutes, **When** the
   dead time and the LHS are learned, **Then** the cycle is excluded from both, even with a
   heating slope of 1.0 °C/h.
2. **Given** a cycle ended by a load shedding (preset `power`, target dropped to the power
   temperature), **When** it is learned, **Then** it is excluded.
3. **Given** a `safety` or `power` preset recorded only before the cycle start or after its end,
   **When** the cycle is learned, **Then** it is included.
4. **Given** a disturbed cycle split into sub-cycles, **When** they are learned, **Then** every
   sub-cycle is excluded.

### User Story 3 — A slow but undisturbed room learns its own slope (Priority: P1)

A room that heats at 0.15 °C/h learns 0.15 °C/h and anticipates accordingly, instead of falling
back to the 2.0 °C/h default.

**Why this priority**: With a floor on the averaged values, learning the slow cycles would still
end in a far too short anticipation.

**Independent Test**: Learn the LHS from undisturbed cycles whose heating slopes are below
0.2 °C/h, then compute an anticipation.

**Acceptance Scenarios**:

1. **Given** an undisturbed cycle with a 90-minute dead time followed by a heating slope of
   0.15 °C/h, **When** the LHS and the dead time are learned, **Then** both include it.
2. **Given** only cycles whose heating slopes average 0.15 °C/h, **When** the global and
   contextual LHS are calculated, stored and used for the anticipation, **Then** 0.15 °C/h is
   used, not the 2.0 °C/h default.
3. **Given** an undisturbed cycle whose heating slope is 0 or negative, **When** it is learned,
   **Then** it is excluded.

### User Story 4 — A cycle that never warmed the room teaches nothing (Priority: P2)

A cycle whose temperature never rises 0.2 °C above its start has no known dead time and no
heating phase, so it is not learned.

**Why this priority**: Without a speed floor, its slope measured from the start would enter the
LHS as a near-zero value.

**Independent Test**: Extract a 20-minute cycle going from 19.7 °C to 19.8 °C and learn from it.

**Acceptance Scenarios**:

1. **Given** a cycle from 19.7 °C to 19.8 °C in 20 minutes, **When** it is extracted, **Then** it
   has no dead time.
2. **Given** that cycle, **When** the dead time and the LHS are learned, **Then** it is excluded
   from both (today it enters the LHS at 0.3 °C/h).
3. **Given** a cycle that falls and never climbs back 0.2 °C above its start, **When** it is
   learned, **Then** it is excluded.

### User Story 5 — Cycles cached before the upgrade keep their former treatment (Priority: P2)

After the upgrade, the cycles already in the cache are learned exactly as before, until they are
re-extracted or leave the retention window.

**Why this priority**: Their disturbance status is unknown; applying "any positive slope" to them
would bring back safety-mode cycles.

**Independent Test**: Load cached cycles that have no disturbance information and learn from
them.

**Acceptance Scenarios**:

1. **Given** a cached cycle without disturbance information and with a slope of 0.15 °C/h,
   **When** the LHS is learned, **Then** it is excluded (former 0.2 °C/h rule).
2. **Given** a cached cycle without disturbance information, without a dead time and with a slope
   of 0.3 °C/h measured from its start, **When** the LHS is learned, **Then** it is included, as
   before.
3. **Given** `reset_learning`, **When** the cycles are re-extracted, **Then** the new rule
   applies to them.

### Edge Cases

- **Non-VTherm climate**: no `power` or `safety` preset is ever recorded. Its cycles are excluded
  only when they never warmed the room or when their heating slope is not positive.
- **Disturbance without a recorded signal** (radiator rooms on 2026-11-02): learned, as accepted
  in the clarifications.
- **Load shedding of 1–3 minutes repeated during a preheat**: each fragment that ends on the
  `power` preset is excluded; the fragment after the last shedding is learned with a dead time
  measured from its own start (#260).
- **Dead time longer than `MAX_ANTICIPATION_TIME`** (only if Maximum Cycle Duration is set above
  360 min): learned; the anticipation is clamped to its maximum as today.
- **Cycle longer than Maximum Cycle Duration**: still discarded whole by the extraction
  (unchanged; see Known Limitations).
- **Preset value case**: the comparison with `power` and `safety` ignores case, as the existing
  `hvac_action` and `hvac_mode` comparisons do.
- **Split cycles**: every sub-cycle carries the disturbance and heating-phase status of its parent
  cycle. Sub-cycles after the first have no dead time by design (#245) and are not excluded for
  that reason.
- **Anticipation using the cycles of the target time's window**: its dead time average applies
  the same rule as the stored dead time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dead time search MUST NOT discard a dead time because of its length. It stays
  bounded by the cycle end (#185).
- **FR-002**: Each extracted cycle MUST record whether it was disturbed: the heating state history
  from its start to its end, both included, contains the preset `power` or `safety`.
- **FR-003**: Each extracted cycle MUST record whether its room gained `DEAD_TIME_TEMP_RISE_C`
  within it, i.e. whether a heating phase was observed. A sub-cycle MUST carry the status of its
  parent cycle.
- **FR-004**: The cycle cache MUST persist both statuses. Cycles cached before this fix MUST load
  with an unknown status.
- **FR-005**: A cycle with a known status MUST be learned only if it is not disturbed, a heating
  phase was observed, and its heating slope is strictly positive.
- **FR-006**: A cycle with an unknown status MUST be learned only if its heating slope is at least
  0.2 °C/h (former rule).
- **FR-007**: FR-005 and FR-006 MUST be the single rule shared by the global LHS, the contextual
  LHS, the stored learned dead time and the dead time averaged by the anticipation.
- **FR-008**: A learned global or contextual LHS MUST be used, stored and loaded whenever it is
  strictly positive. The 2.0 °C/h default MUST apply only when no learned value exists or it is
  not positive.
- **FR-009**: The anticipation formula MUST stay `dead_time + Δ / LHS`, clamped to
  `[MIN_ANTICIPATION_TIME, MAX_ANTICIPATION_TIME]`.

### Key Entities

- **Heating cycle**: gains two optional statuses: disturbed (by load shedding or safety mode),
  and heating phase observed. Both are absent from cycles cached before this fix.
- **Learning rule**: the single rule deciding which cycles teach the dead time and the LHS.
  Disturbance and heating phase decide for new cycles; the former speed floor survives only for
  cycles whose status is unknown.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the issue's reproduction, the living room cycles of 2026-10-30 and 2026-10-31 are
  learned with dead times of 202 and 243 minutes and heating slopes of 1.11 and 0.65 °C/h (today:
  dead times dropped, 2026-10-31 rejected).
- **SC-002**: A room whose undisturbed cycles all heat below 0.2 °C/h learns a slope and a dead
  time instead of the 2.0 °C/h and configured defaults.
- **SC-003**: 0 cycles extracted after the fix that contain a `power` or `safety` preset, or that
  never gained 0.2 °C, take part in learning.
- **SC-004**: Learning from cycles cached before the fix gives the same dead time and LHS as
  before the fix.

## Assumptions

- VTherm reports load shedding and safety mode through its `preset_mode` attribute, with the
  values `power` and `safety`, and records that attribute (VTherm 6 and later, verified on
  10.6.3).
- Indoor temperatures are reported with at least 0.1 °C resolution, so a cycle that warms the
  room reaches `start_temp + 0.2 °C` within it.
- The heating state history used for cycle extraction keeps the climate attributes of each
  record, as it does today for `hvac_action` and `hvac_mode`.

## Known Limitations

- Disturbances that leave no recorded signal (heater shed by an external device, open window
  without a window sensor, sun, occupancy) are learned.
- A cycle longer than the Maximum Cycle Duration setting (300 min by default) is still discarded
  whole. Underfloor heating users whose preheats exceed it need to raise the setting.
- A preheat fragmented by brief interruptions learns the dead time of its last fragment only
  (#260).
- Cycles cached before the fix keep the 180-minute cap they were extracted with, until
  `reset_learning` re-extracts them or they leave the retention window.
- A slope below 0.2 °C/h stored by an earlier version is used until the next recalculation
  (next extraction or daily refresh).

## Out of Scope

- Bridging brief interruptions within one cycle (#260).
- Using `power_percent` to tell a disturbed cycle from a slow one.
- Changing the default Maximum Cycle Duration.
