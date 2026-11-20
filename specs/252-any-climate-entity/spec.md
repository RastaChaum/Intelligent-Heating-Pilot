# Feature Specification: Support any climate entity, VTherm recommended but optional

**Feature Branch**: `252-any-climate-entity`
**Issue**: #252
**Status**: Draft

## Principle

Any `climate` entity can be selected and preheated. Versatile Thermostat (VTherm) stays the
best-supported target: its capabilities (preset temperatures, specific states, a future
`tpi_coef_ext` prior) are detected at runtime and used when present, never required.

## Clarifications

### Session 2026-11-20

- Q: How are preset-based slots resolved on a climate that does not publish preset
  temperatures? → A: The user maps each preset to a temperature in the device options
  (option b of the issue). Resolution order: what the climate publishes, then the user
  mapping, then unresolved.
- Q: What happens to a climate without `hvac_action`? → A: It is accepted and preheated,
  but no heating cycle is learned from it, and a single warning says why.
- Finding: the issue assumed such a climate would count its whole `heat` period as active
  heating. In production, history records without `hvac_action` are dropped at read time,
  so the extraction fails for the period instead (an error per period). The behaviour to
  deliver is therefore a graceful, explained "no learning", not the removal of a state
  fallback (that fallback only serves non-climate sources and stays).
- Coordination: #302 (menus and central defaults) restructures the same options flow. The
  preset mapping is device-specific and never inherited; see the comment on #302.

## User Scenarios

### User Story 1 - Select any climate (Priority: P1)

As a user without VTherm, I pick my own `climate` entity when I create or edit an IHP device.

1. **Given** a `climate` entity of any integration, **When** I create a device, **Then** it
   is offered by the thermostat selector and the device is created.
2. **Given** an existing device on a VTherm, **When** the integration upgrades, **Then**
   nothing changes (same stored key, same behaviour).

### User Story 2 - Presets on a generic climate (Priority: P2)

As a user whose climate exposes `preset_modes` but not their temperatures, I tell IHP which
temperature each preset stands for, so slots that set a preset are anticipated.

1. **Given** a HACS Scheduler slot using `climate.set_preset_mode` and a mapping for that
   preset, **Then** the anticipation uses the mapped temperature.
2. **Given** a native `schedule.*` block mapped to a preset with a mapping, **Then** the
   mapped temperature replaces the 20 °C default.
3. **Given** a preset the climate does not publish and the user did not map, **Then** the
   slot is not anticipated and one warning names the preset and the climate.
4. **Given** a VTherm that publishes preset temperatures, **Then** they win over the
   mapping.
5. **Given** a device whose climate exposes no `preset_modes`, **Then** the options flow
   does not show the mapping step.

### User Story 3 - Climate without `hvac_action` (Priority: P3)

1. **Given** a climate that never publishes `hvac_action`, **When** history extraction runs,
   **Then** no cycle is extracted, no error is raised, and one warning explains that
   learning needs `hvac_action`.
2. **Given** that same climate, **Then** preheating still runs with the default or the
   user-set learned heating slope.

### User Story 4 - Neutral vocabulary and cleanup (Priority: P3)

Internal names no longer say "VTherm" where any climate is meant, and dead code is removed.

## Requirements

- **FR-001**: Both thermostat selectors (config flow and options flow) MUST accept any
  `climate` entity.
- **FR-002**: The stored config key `vtherm_entity_id` MUST NOT change; no migration.
- **FR-003**: The device options MUST offer a preset-to-temperature mapping step, shown only
  when the climate exposes `preset_modes`, reachable like the wake-up sources step.
- **FR-004**: Preset resolution MUST try, in order: temperatures published by the climate,
  the user mapping, then report unresolved.
- **FR-005**: An unresolved preset MUST be logged once per preset and climate, at WARNING.
- **FR-006**: A climate without `hvac_action` MUST yield no cycle and one WARNING per device
  and run, never one ERROR per period.
- **FR-007**: Domain vocabulary MUST use `climate_entity_id` (`DeviceConfig`) and
  `get_climate_entity_id()` (`IClimateDataReader`); `vtherm_compat` helpers that read standard
  attributes MUST be renamed to neutral names.
- **FR-008**: `IClimateDataReader.get_current_slope()` and `VTHERM_ATTR_SLOPE` MUST be
  removed with their tests.
- **FR-009**: Every new label and help text MUST exist in English and French.
- **FR-010**: README, `README.fr.md` and `docs/` MUST present VTherm as recommended, not
  required, and list what a generic climate must expose.
- **FR-011**: The domain layer MUST NOT import `homeassistant.*`.

## Out of Scope

- Adopting `vtherm_api` (Python 3.14+, regulation-oriented, would be imposed on every user).
- Actuation (#249).
- Learning the target observed per preset (option c) and a repair-issue UI for the
  warnings.

## Success Criteria

- A non-VTherm climate can be selected, preheated from `set_temperature` slots, and from
  preset slots once mapped.
- No existing VTherm device changes behaviour.
- The full test suite and the translation parity test pass.
