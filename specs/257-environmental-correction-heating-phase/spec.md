---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: The Environmental Correction Applies to the Heating Phase in Daylight Only

**Feature Branch**: `fix/issue-257-environmental-correction`
**Created**: 2026-11-03
**Status**: Draft
**Input**: GitHub issue #257 — "Environmental correction shortens the dead time and assumes solar
gain before sunrise"

## Context

`PredictionService.predict_heating_time` multiplies the whole anticipation, dead time included, by
the environmental correction:

```text
anticipation = (dead_time + ΔT / LHS × 60) × humidity_factor × solar_factor + buffer
```

- The dead time is a property of the emitter: the time before the room responds, learned from
  cycles. Sun or humidity does not make the emitter respond faster.
- `solar_factor` comes from the current cloud coverage and assumes solar gain whenever the sky is
  clear, at night included, for preheats that end before the sun is up.

### What the sensors show (2026-11-01, IHP v0.7.1-rc1)

Calculation at 06:00, before sunrise, clear sky, indoor humidity ≈ 60 %: correction 0.92
(solar 0.90 × humidity 1.02). Anticipation 154 min instead of 167 min without correction: the
preheat was planned 13 min late, about 7 min of it taken from the 85.8 min dead time.

## Clarifications

### Session 2026-11-03

- Q: Where does IHP learn whether the sun is up? → A: From the sunrise and sunset times of the
  Home Assistant location (`homeassistant.helpers.sun`), behind a domain interface. This works
  even when the `sun.sun` entity is disabled, and needs no new setting.
- Q: A heating phase that straddles sunrise or sunset? → A: Pro rata. The solar shortening is
  scaled by the share of the heating phase spent in daylight: 30 % of the phase in daylight gets
  30 % of the solar shortening. The anticipation then varies smoothly around sunrise.
- Q: Keep the humidity factor? Use a cloud forecast? → A: The humidity factor stays, applied to
  the heating phase only. The cloud coverage stays the current value; the weather reader exposes
  no hourly forecast.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The dead time is never shortened (Priority: P1)

**Why this priority**: The dead time is learned from cycles; shortening it plans every corrected
preheat late, by up to 20 % of the dead time.

**Independent Test**: Predict a preheat with a dead time, a humidity and a clear sky in daylight,
and check that the corrected anticipation equals the dead time plus the corrected heating phase.

**Acceptance Scenarios**:

1. **Given** a learned dead time of 60 min, a heating phase of 60 min, a clear sky in daylight
   and 50 % humidity, **When** IHP computes the anticipation, **Then** it is 60 + 60 × 0.9 + 5 =
   119 min.

### User Story 2 — No solar gain before sunrise (Priority: P1)

**Why this priority**: This is the 2026-11-01 case: every winter morning preheat ends before
sunrise, and a clear sky made all of them late.

**Acceptance Scenarios**:

1. **Given** a preheat for 07:00 with sunrise at 07:50 and a clear sky, **When** IHP computes the
   anticipation, **Then** it is the same as under a fully overcast sky.
2. **Given** the 2026-11-01 case (dead time 85.8 min, heating phase 76.2 min, humidity 60 %, clear
   sky, preheat ending before sunrise), **When** IHP computes the anticipation, **Then** it is
   85.8 + 76.2 × 1.02 + 5 ≈ 168.5 min, no longer 154 min.
3. **Given** a heating phase that ends 30 min after sunrise and lasts 60 min, **When** IHP computes
   the anticipation under a clear sky, **Then** half of the solar shortening applies.

### Edge Cases

- No cloud coverage source: no solar factor, sunrise and sunset are not read.
- Sun data unavailable (no daylight period returned): no solar gain. A preheat planned a little
  early is better than a late one.
- Polar night or polar day (no sunrise or sunset on a date): no daylight period for that date, so
  no solar gain.
- A heating phase spanning midnight or two days: the daylight periods of every date it touches are
  considered.
- No humidity source: the reader already falls back to 50 %, a neutral factor.
- MIN/MAX anticipation limits apply after the correction, as today.

## Requirements *(mandatory)*

- **FR-001**: The anticipation is `dead_time + heating × humidity_factor × solar_factor_effective +
  buffer`, where `heating = ΔT / LHS × 60`. The dead time is never corrected.
- **FR-002**: The heating phase window is `[target_time − heating, target_time]`, using the
  uncorrected heating duration (the correction is within ±20 %, so the window barely moves).
- **FR-003**: `solar_factor_effective = 1 − (1 − solar_factor) × daylight_fraction`, where
  `daylight_fraction` is the share of the heating phase window covered by daylight periods.
- **FR-004**: Daylight periods come from a domain interface `ISunReader`; the HA adapter only
  translates sunrise and sunset times of each local date into `DaylightPeriod` value objects.
- **FR-005**: No daylight period known → no solar shortening.
- **FR-006**: `CalculateAnticipationUseCase` reads daylight periods over the longest possible
  anticipation before the target time, and only when a cloud coverage is known.

## Out of Scope

- An hourly cloud forecast over the heating window.
- Removing or learning the humidity factor.
- Orientation of the room (east/west windows) or the sun's elevation beyond above/below horizon.

## Success Criteria

- **SC-001**: The 2026-11-01 case gives ≈ 168.5 min instead of 154 min.
- **SC-002**: Corrections never change the dead time part of the anticipation.
