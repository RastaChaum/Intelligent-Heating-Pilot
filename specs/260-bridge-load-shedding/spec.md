---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: A Brief Load Shedding Does Not Restart the Heating Cycle

**Feature Branch**: `fix/issue-260-bridge-load-shedding`
**Created**: 2026-11-03
**Status**: Draft
**Input**: GitHub issue #260 — "A brief interruption (load shedding, window, hvac off) restarts the
heating cycle, so the dead time is learned from the last fragment"

## Context

IHP extracts heating cycles from the Recorder history of the thermostat
(`HeatingCycleService.extract_heating_cycles`). A cycle ends when the room is within the
configured delta of the **current** target, or when `hvac_mode` leaves the heating modes. A grace
period (`safety_shutoff_grace_minutes`, 10 minutes by default in the options) already bridges an
`hvac_mode` off shorter than the grace period. It does not cover target drops.

During load shedding, Versatile Thermostat sets the preset to `power` and drops the target to its
power temperature for one to a few minutes. The room is then above the current target, so the
cycle ends. When the preset comes back, a new cycle starts, and its dead time is measured from that
fragment's start. The fragments before it are short, flat and not learned, so the slow start they
cover is lost.

Since #255, a cycle during which `power` or `safety` is recorded is "disturbed" and not learned.
That rule excludes the fragments ended by load shedding, but the last fragment is still learned with
a dead time that is too short.

### What the history shows (living room, `climate.thermostat_salle`, 2026-11-02, grace 10 min)

| Time | Preset | Target | Effect today |
|---|---|---|---|
| 04:09:18 | `power` (IHP has just requested comfort) | 16 °C | no cycle yet |
| 04:12:07 | `comfort` | 20 °C | cycle 1 starts at 19.1 °C |
| 04:29:18 → 04:31:12 | `power` | 16 °C | cycle 1 ends (17 min); cycle 2 starts 04:31 |
| 04:49:18 → 04:50:17 | `power` | 16 °C | cycle 2 ends (18 min); cycle 3 starts 04:50 |
| 05:09:18 → 05:21:24 | `power` six times, each for 1–3 min, `comfort` for 1 min between them | 16 / 20 °C | cycle 3 ends (19 min); micro-cycles below the minimum duration |
| 05:21:24 | `comfort` | 20 °C | cycle 4 starts; dead time learned 73 min |

Every load shedding lasts less than the grace period. Bridged, they give a single cycle from
04:12, whose dead time is ≈ 142 minutes. The same load shedding fragmented the preheats of all
8 VTherms that night.

## Clarifications

### Session 2026-11-03

- Q: Which interruptions are bridged? → A: Load shedding only, i.e. the VTherm preset `power`.
  A window opening (target dropped to the window action temperature) still ends the cycle at once:
  the room really cools down and the cycle is not representative. `hvac_mode` off keeps its current
  grace period behaviour.
- Q: Which threshold bounds a bridged load shedding? → A: The existing grace period
  (`safety_shutoff_grace_minutes`). No new option. A load shedding shorter than it is bridged; a
  longer one ends the cycle at the moment the shedding started, like an `hvac_mode` off that
  outlasts the grace period. With a grace period of 0, nothing is bridged (current behaviour).
- Q: Subtract the interrupted minutes from the dead time and the heating phase? → A: No. The dead
  time runs from the start of the cycle to the first reading 0.2 °C above its start, load sheddings
  included. The error is bounded by the grace period, and the heating keeps warming the room while
  the switch is shed (underfloor slab).
- Q: Is a cycle containing a bridged load shedding learned? → A: Yes. A bridged load shedding does
  not make the cycle disturbed. A load shedding that ends the cycle (longer than the grace period,
  or with a grace period of 0) still does (#255), and so does the `safety` preset anywhere in the
  cycle.
- Q: Cycles already in the cache? → A: They keep their fragments until they leave the retention
  window or `reset_learning` re-extracts them from the Recorder.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A preheat interrupted by brief load sheddings is learned as one cycle (Priority: P1)

A room whose preheat is shed several times for a minute or two learns the dead time measured from
when its heating really started.

**Why this priority**: Every room of a house with load shedding learns a dead time that is too
short on the coldest mornings, when the power demand is highest, so its next preheats start late.

**Independent Test**: Extract a preheat whose preset is `power` (target dropped) for 2 minutes,
twice, before the room starts warming, and learn the dead time.

**Acceptance Scenarios**:

1. **Given** a preheat from 19.1 °C to 20 °C starting at 04:12, shed for 2 minutes at 04:29 and
   for 1 minute at 04:49, whose room gains 0.2 °C at 06:34, **When** the cycles are extracted with
   a grace period of 10 minutes, **Then** a single cycle starts at 04:12 and its dead time is
   142 minutes.
2. **Given** that cycle, **When** the dead time and the heating slope are learned, **Then** both
   include it.
3. **Given** a preheat shed six times for 1–3 minutes with 1 minute of comfort between them,
   **When** it is extracted, **Then** it is a single cycle.

### User Story 2 — A long load shedding still ends the cycle (Priority: P1)

A load shedding longer than the grace period ends the cycle when it started, and the cycle stays
excluded from learning.

**Why this priority**: A long shedding lets the room cool; the cycle no longer describes how the
room heats.

**Acceptance Scenarios**:

1. **Given** a cycle shed for 15 minutes with a grace period of 10 minutes, **When** it is
   extracted, **Then** the cycle ends when the shedding started and is disturbed.
2. **Given** a cycle shed for 2 minutes with a grace period of 0, **When** it is extracted,
   **Then** the cycle ends when the shedding started and is disturbed (current behaviour).
3. **Given** a history that ends during a load shedding, **When** it is extracted, **Then** the
   cycle ends when the shedding started.

### User Story 3 — Other interruptions are unchanged (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a target dropped to the frost temperature by a window for 2 minutes, without the
   `power` preset, **When** the cycle is extracted, **Then** the cycle ends at the drop.
2. **Given** a cycle with a bridged load shedding and the `safety` preset elsewhere in it, **When**
   it is extracted, **Then** it is disturbed.

### Edge Cases

- **Several load sheddings in a row**: each one is bounded by the grace period on its own; the time
  between them does not matter.
- **The preset comes back to another target** (the schedule changed during the shedding): the
  cycle-end rule applies to the first record after the shedding, as it does after a bridged
  `hvac_mode` off.
- **`hvac_mode` off during a load shedding**: one interruption, bounded by the grace period from
  its first record.
- **Non-VTherm climate**: no `power` preset is recorded; nothing changes.
- **Preset case**: `power` is compared case-insensitively, as in #255.
- **Split cycles**: every sub-cycle carries the disturbance status of its cycle (#255).
- **Late preheat slot** (#254): a bridged preheat is one cycle, so a slot coming due during any of
  its former fragments is tied to it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: During a cycle, a heating state record whose preset is `power` MUST start an
  interruption, like an `hvac_mode` off, when the grace period is positive.
- **FR-002**: An interruption whose first record without `power` (and with `hvac_mode` on) comes
  less than the grace period after its start MUST be bridged: the cycle continues, and the
  cycle-end rule applies from that record on.
- **FR-003**: An interruption that lasts at least the grace period, or that is still running when
  the history ends, MUST end the cycle at the interruption start.
- **FR-004**: A `power` record within a bridged interruption MUST NOT make the cycle disturbed.
  Every other `power` or `safety` record of the cycle, both bounds included, still does (#255).
- **FR-005**: A target drop without the `power` preset MUST keep ending the cycle at once.
- **FR-006**: The dead time and the heating phase MUST be measured from the cycle start, bridged
  interruptions included.

### Key Entities

- **Heating cycle**: unchanged. It can now span brief load sheddings; no new persisted field.
- **Interruption**: a run of heating state records with `hvac_mode` off or the `power` preset,
  within a cycle, bounded by the grace period.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the 2026-11-02 living room history, the preheat is extracted as one cycle
  starting at 04:12, with a dead time of ≈ 142 minutes (today: 73 minutes from the 05:21 fragment),
  and it is learned.
- **SC-002**: 0 cycles ended by a load shedding take part in learning (unchanged from #255).
- **SC-003**: With a grace period of 0, or on a non-VTherm climate, the extracted cycles are
  identical to those before the fix.

## Assumptions

- VTherm records the `power` preset for the whole load shedding and restores the previous preset
  afterwards (verified on VTherm 10.6.3 and the live Recorder).
- The grace period is configured per device; its default is 10 minutes.

## Known Limitations

- A load shedding longer than the grace period still fragments the preheat.
- Window openings and other target drops still fragment the preheat (2026-10-28: window then
  `hvac_mode` off for 28 minutes).
- Cycles already cached keep their fragments until `reset_learning` or the end of the retention
  window.

## Out of Scope

- Bridging window openings or other target drops.
- Subtracting the interrupted minutes from the dead time or the heating phase.
- A separate threshold for load shedding.
