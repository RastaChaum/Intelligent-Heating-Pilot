---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Configuration menus and central default configuration

**Feature Branch**: `302-config-menus-central-defaults`
**Created**: 2026-11-20
**Status**: Draft
**Input**: User description: "Reorganise the IHP configuration screens into menus and sub-menus by theme, and add a central default configuration that every device inherits unless it overrides a value (#302)"

## Principle

A user changing one thing should see only that thing. A value that is the same for every
device should be entered once. Each device keeps full control: it can always override a
central value, and always go back to following it.

The feature is delivered in two independent steps: the menus first (User Story 1), the
central default configuration second (User Stories 2 and 3).

## Clarifications

### Session 2026-11-20

- Q: Is the native schedule drive shareable centrally? → A: No, per device only.
- Q: How is the central configuration created? → A: Automatically with the first device.
- Q: What does device creation store for shareable values? → A: Only device-specific fields; every shareable value is inherited, with no override.
- Q: Where does the user edit the central configuration? → A: A dedicated visible entry whose configure button opens the theme menus, without device-specific fields.
- Q: Can the central configuration be deleted while devices exist? → A: No, deletion is refused until no device remains.
- Q: When do devices pick up a changed central value? → A: Once, when the user leaves the central menus, and only devices whose inherited value changed.

## User Scenarios & Testing *(mandatory)*

Constitution-driven test requirements:

- Every user story MUST include at least one BDD scenario written in Gherkin.
- Every user story MUST define technical validation for the failure, boundary, or
  algorithmic risks that are actually relevant to that story.

### User Story 1 - Navigate device settings by theme (Priority: P1)

A user opens the options of a device and lands on a menu listing the themes
(thermostat and schedulers, wake-up sources, environment sensors, learning, cycle
detection, anticipation behaviour). Choosing a theme opens a form with only the fields of
that theme. Saving returns to the menu, where the user can pick another theme or leave.

**Why this priority**: it removes the single long mixed form and stands alone. It changes
no stored value and no runtime behaviour, so it can ship first.

**Independent Test**: open the options of an existing device, open one theme, change one
value, save, and check that the value is stored and every other value is unchanged.

**Acceptance Scenarios**:

1. **Given** an existing device, **When** the user opens its options, **Then** a menu of
   themes is shown and no setting field is shown yet.
2. **Given** the theme menu, **When** the user opens "Learning" and saves a new retention,
   **Then** only the retention changes and the menu is shown again.
3. **Given** a theme form, **When** the user leaves without saving, **Then** nothing changes.
4. **Given** the menu, **When** the user opens "Wake-up sources", **Then** the existing
   wake-up sources flow behaves as before.
5. **Given** a theme form with an invalid value, **When** the user saves, **Then** the form
   stays open with the error next to the field and no value is stored.

```gherkin
Feature: Device options grouped by theme
  Scenario: Change one setting from its theme
    Given an IHP device with a data retention of 30 days
    When I open the device options and choose the "Learning" theme
    And I set the data retention to 60 days and save
    Then the options menu is shown again
    And the data retention of the device is 60 days
    And no other setting of the device has changed
```

**Technical validation**: invalid and out-of-range values per theme; leaving a form without
saving; saving two themes in a row keeps both changes; every theme and menu entry has an
English and a French label.

---

### User Story 2 - Set values once for all devices (Priority: P2)

A user with several devices opens a central configuration from the integration and sets
the values shared by all devices: environment sensors, learning and cycle parameters,
safety grace period, native schedule keys. Every device that has not overridden a value
follows the central one, including devices created later.

**Why this priority**: it is the main time saver for multi-device setups, but it depends on
the theme structure of User Story 1 for its own screens.

**Independent Test**: with two devices that override nothing, set the outdoor temperature
sensor centrally and check that both devices use it.

**Acceptance Scenarios**:

1. **Given** two devices without overrides, **When** the user changes a central value,
   **Then** both devices use the new value without being edited.
2. **Given** a new device is created, **When** the user completes the creation screen,
   **Then** the device holds no override and follows every central value.
3. **Given** a device that overrides a value, **When** the central value changes, **Then**
   that device keeps its own value.
4. **Given** no central configuration has ever been set, **When** a device runs, **Then** it
   uses the built-in defaults exactly as today.

```gherkin
Feature: Central default configuration
  Scenario: A central value reaches devices that do not override it
    Given two IHP devices that override no setting
    And a central outdoor temperature sensor "sensor.outdoor_a"
    When I change the central outdoor temperature sensor to "sensor.outdoor_b"
    Then both devices use "sensor.outdoor_b"
```

**Technical validation**: central value changes are applied to inheriting devices only; no
central configuration present; central configuration removed while devices exist; a central
value that is invalid or points to a missing entity.

---

### User Story 3 - See, override and reset a device value (Priority: P3)

In a theme form of a device, the user can tell for each shareable value whether it is
inherited from the central configuration or overridden for this device. The user can
override it, and can go back to "inherit".

**Why this priority**: it makes inheritance understandable and reversible; the central
configuration is usable without it, but unclear.

**Independent Test**: override one value on one device, check it is marked as overridden,
reset it to inherit, and check it now follows the central value.

**Acceptance Scenarios**:

1. **Given** an inheriting value, **When** the user opens its theme, **Then** it is shown as
   inherited together with the central value it resolves to.
2. **Given** an inheriting value, **When** the user enters a different value and saves,
   **Then** it becomes an override and is marked as such.
3. **Given** an overridden value, **When** the user chooses "inherit" and saves, **Then**
   the device follows the central value again.
4. **Given** a device-specific setting (thermostat, schedulers, wake-up sources),
   **When** the user opens its theme, **Then** it has no inherit option.

```gherkin
Feature: Inherit, override and reset a device value
  Scenario: Reset an override to the central value
    Given a central data retention of 30 days
    And an IHP device that overrides its data retention with 90 days
    When I set the data retention of the device back to "inherit" and save
    Then the device uses a data retention of 30 days
```

**Technical validation**: a value equal to the central one is still an override until reset;
reset when no central value exists falls back to the built-in default; a central value
changes while the device form is open.

---

### Edge Cases

- The user tries to delete the central configuration while devices exist: the deletion is
  refused with an explanation, and no device changes.
- Installations upgraded from a version without central configuration have devices but no
  central values yet: devices behave exactly as before until central values are set.
- A central value is cleared (for example the outdoor sensor): inheriting devices behave as
  if the sensor was never configured.
- A central sensor entity is unavailable or deleted: handled like a device-level sensor that
  is unavailable today.
- Two edits happen at once (central value and device form): the last saved value wins and
  no partial state is stored.
- Existing devices after an upgrade: every value they already hold becomes an explicit
  override, so no behaviour changes.
- A device is added when the central configuration does not exist yet.
- Out-of-range values are rejected in the central configuration with the same rules as at
  device level.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Device options MUST open on a menu of themes, and each theme MUST open a form
  containing only the fields of that theme.
- **FR-002**: Themes MUST be: thermostat and schedulers, wake-up sources, environment
  sensors, learning, cycle detection, anticipation behaviour; the final grouping may be
  refined in the plan without moving a setting out of its theme's intent.
- **FR-003**: Saving a theme form MUST return to the menu, and the user MUST be able to
  leave the menu at any time; unsaved changes in a form MUST NOT be stored.
- **FR-004**: The existing wake-up sources flow MUST keep its behaviour and be reachable from
  the menu.
- **FR-005**: Each theme form MUST apply the same validation as the current single form.
- **FR-006**: The integration MUST offer a central configuration holding the shareable values:
  environment sensors, learning and cycle parameters, safety grace period, native schedule
  keys.
  The native schedule drive opt-in (#281) is NOT shareable: it stays a per-device decision
  because it lets IHP act on the climate.
- **FR-007**: A device MUST resolve each shareable value as: its own override if present, else
  the central value if present, else the built-in default.
- **FR-008**: Device-specific values (thermostat, schedulers, wake-up sources) MUST NOT be
  inheritable.
- **FR-009**: A central value change MUST reach every device that inherits it without the user
  editing those devices, and MUST NOT affect devices that override it. Devices MUST pick up
  changes once, when the user leaves the central menus, and only devices whose inherited
  value actually changed MUST be reloaded.
- **FR-010**: A device theme form MUST show, per shareable value, whether it is inherited or
  overridden, and the central value an inherited one resolves to.
- **FR-011**: The user MUST be able to reset any overridden value to "inherit".
- **FR-012**: Upgrading MUST convert every value held by an existing device into an explicit
  override so that no existing behaviour changes.
- **FR-013**: When no central configuration exists, devices MUST behave exactly as before the
  feature.
- **FR-014**: Creating the central configuration MUST be possible when devices already exist
  and when none exist.
  The central configuration MUST be created automatically with the first device, and MUST
  survive the deletion of devices.
- **FR-015**: Every menu entry, theme, field label, help text and inherit/override indicator
  MUST have an English and a French translation (#193).
- **FR-016**: Delivery MUST allow shipping the menus (User Story 1) without the central
  configuration.
- **FR-017**: System MUST define clear domain/infrastructure boundaries consistent
  with hexagonal architecture and DDD: resolution of inherited values is a domain rule,
  while reading and writing configuration entries stays in infrastructure.
- **FR-018**: System MUST describe how decoupled services communicate through
  Home Assistant events (emission + subscription): a central value change is announced so
  that only inheriting devices react; no new event is expected for the menus.
- **FR-019**: System MUST provide explicit typing expectations for all public
  interfaces involved in the feature, including the resolved-settings carrier.
- **FR-020**: System MUST identify any logging obligations introduced or changed by the
  feature: INFO when a central value is changed and when a device override is set or reset,
  DEBUG for value resolution, using device friendly names.
- **FR-021**: System MUST state whether new services remain stateless: value resolution is
  stateless; the stored central and device values are the only state.
- **FR-022**: Device creation MUST ask only for device-specific values (name, thermostat,
  schedulers) and MUST store no override: every shareable value is inherited until the user
  overrides it from a theme menu.
- **FR-023**: The central configuration MUST appear as its own entry in the integration list
  under an explicit name, deletion MUST be refused while at least one device exists, and
  its configure action MUST open the same theme menus as a
  device, limited to shareable themes and without device-specific fields.

### Workflow Requirements *(mandatory)*

- **WR-001**: The specification names `speckit.specify` as producer and `speckit.clarify` as
  critical reviewer.
- **WR-002**: The expected reviewers are `speckit.checklist` for the plan, `speckit.analyze`
  for the tasks, and `speckit.review` for the implementation.
- **WR-003**: Any unresolved reviewer challenge MUST be tracked explicitly before
  implementation begins.

### Documentation Requirements *(mandatory)*

- **DR-001**: The user guides under `docs/` MUST describe the theme menu, the central
  configuration, and how to override and reset a value.
- **DR-002**: Contributor documentation MUST describe how a setting is declared as shareable
  or device-specific.
- **DR-003**: All new or updated documentation and code artifacts MUST be in English,
  except `README.fr.md`, which MUST be updated whenever `README.md` changes.
- **DR-004**: Documentation changes MUST avoid duplicated guidance and ad-hoc
  markdown reports unless explicitly requested.

### Key Entities *(include if feature involves data)*

- **Central configuration**: the set of shareable values that apply to every device by
  default; at most one per installation.
- **Device configuration**: the values of one device, split into device-specific values and
  optional overrides of shareable values.
- **Override**: a shareable value explicitly set on a device; absence of an override means
  "inherit".
- **Resolved settings**: the effective value of each setting for a device after applying
  override, then central value, then built-in default.
- **Theme**: a named group of related settings shown as one form.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can change one setting of a device by opening at most one menu and one
  form, and sees no more than the fields of that theme (at most 8 fields).
- **SC-002**: Changing a value shared by 8 devices takes one edit instead of 8.
- **SC-003**: After an upgrade, 100% of existing devices run with the same effective values
  as before.
- **SC-004**: For every shareable value, a user can tell whether it is inherited or
  overridden without leaving the theme form.
- **SC-005**: 100% of menu entries, themes and fields are available in English and French.

## Assumptions

- The central configuration is a single installation-wide set of values, not several named
  profiles.
- Reloading a device that inherits a changed central value is acceptable, as it is for a
  device option change today; devices whose values did not change are not reloaded.
- Wake-up sources, thermostat and schedulers stay per device in all cases.
- The device creation screen asks only for device-specific values; shareable values are set
  afterwards in the theme menus (overrides) or in the central configuration.
- Menus ship first as their own pull request, the central configuration in a following one,
  both under this specification.
- Refusing deletion of the central entry may not be technically possible with the platform's
  entry removal; if the plan shows it is not, the fallback is to allow deletion, fall back to
  built-in defaults for inherited values, and recreate the entry at the next device creation
  or startup. The plan MUST settle this.
- The existing "copy settings from another device" idea is out of scope.
