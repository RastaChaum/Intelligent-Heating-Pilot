---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Setup, Config-Flow and Lifecycle Robustness

**Feature Branch**: `fix/issue-192-setup-lifecycle`
**Created**: 2026-11-05
**Status**: Draft
**Input**: GitHub issue #192 — "[BUG] Setup, config-flow and lifecycle robustness"

## Context

The October 2026 full-code review found six weaknesses in how a device is created, edited, loaded
and unloaded. None of them breaks a single-device install that is never edited, which is why they
went unnoticed. Each one shows up when a user edits, reloads, removes or duplicates a device.

| # | Weakness | Where |
|---|---|---|
| 1 | A configured scheduler that no longer exists blocks saving the options | `config_flow.py`, options flow |
| 2 | Devices are keyed on their name, not on their VTherm | `config_flow.py`, user step |
| 3 | The `EVENT_HOMEASSISTANT_STARTED` listener survives an unload | `__init__.py`, `async_setup_entry` |
| 4 | The manifest declares no dependency although `http` and `recorder` are used | `manifest.json` |
| 5 | The coordinator is cleaned up before the platforms are unloaded | `__init__.py`, `async_unload_entry` |
| 6 | Services are registered by the first entry and never unregistered | `__init__.py`, `async_setup_entry` |

### What the code shows

1. **Confirmed.** The options flow builds a `SelectSelector` from the `switch.*` and `schedule.*`
   states that exist when the form opens, and uses the configured schedulers as its default.
   `SelectSelector.__call__` (Home Assistant 2026.1) validates each value with
   `vol.In(options)`. A scheduler that was removed or renamed is in the default but not in the
   options, so submitting the form fails, whatever field the user changed. The only way out is
   to clear the scheduler field first, without being told which entry is stale.
2. `async_set_unique_id(name)` makes a second device keeping the default name "Intelligent
   Heating Pilot" abort as already configured, while the same VTherm can be configured twice
   under two names. Two devices driving the same VTherm fight over its setpoint. Entities,
   device identifiers and storage files are keyed on `entry_id`, so two devices sharing a name
   are otherwise harmless.
3. `hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, ...)` is not tied to the entry. If
   the entry is reloaded or removed before Home Assistant finishes starting, the old coordinator
   still schedules its first update and its cycle extraction.
4. `async_setup` writes `hass.http.app`, and four adapters call `recorder.get_instance`. Without
   declared dependencies Home Assistant may set the integration up before either is loaded.
5. `async_unload_entry` calls `coordinator.async_cleanup()` before `async_unload_platforms`. If
   the platforms fail to unload, the entry stays loaded with a coordinator whose listeners are
   gone: its sensors keep showing values that no longer update.
6. `reset_learning` and `calculate_anticipated_start_time` are registered inside
   `async_setup_entry`, guarded by `has_service`, and stay registered after the last device is
   removed.

## Clarifications

### Session 2026-11-05

- Q: What should the options form do with a scheduler that no longer exists? → A: Keep it
  selectable, labelled as not found (`<entity_id> (not found)`), so the form can be saved as is
  and the user sees which entry to remove. It is not removed silently: a scheduler can be
  missing only for a moment (integration still loading, entity being renamed).
- Q: Does the setup form need the same fix? → A: No. It has no configured scheduler to show.
  Both forms build their options with the same helper, so they stay identical.
- Q: What identifies a device? → A: Its VTherm. A VTherm already driven by another device is
  refused: the setup form aborts with `already_configured`, and the options form shows
  `vtherm_already_configured` on the VTherm field. Two devices may share a name.
- Q: Which VTherm is compared? → A: The one in use: the options value when set, else the setup
  value, as `HADeviceConfigReader` reads it.
- Q: What becomes of the `unique_id`? → A: A new device takes its VTherm entity id. When the
  options form changes the VTherm, the `unique_id` follows it, so no two entries ever share a
  `unique_id`. Existing devices keep their name-based `unique_id` until their VTherm is
  changed: duplicates are detected on the VTherm in use, not on the `unique_id`, so no
  migration is needed.
- Q: How is the start listener tied to the entry? → A: With `homeassistant.helpers.start.
  async_at_started`, registered through `entry.async_on_unload`. Its cancel callback is safe to
  call after the event has fired, unlike the raw `async_listen_once` remover, which logs an
  error then. It also replaces the `hass.is_running` branch: the startup work now waits for
  `EVENT_HOMEASSISTANT_STARTED` when the entry is set up while Home Assistant is still starting,
  which is what the existing comment intends ("Wait for HA to be fully started").
- Q: Should `http` stay a dependency, given #200 plans to remove `view.py`? → A: Yes for now:
  `async_setup` still writes `hass.http.app`. #200 removes both together.
- Q: What if the platforms fail to unload? → A: The entry stays loaded with a working
  coordinator. The coordinator is cleaned up and removed from `hass.data` only once the
  platforms are unloaded.
- Q: Should the services be unregistered when the last device is removed? → A: No: they move to
  `async_setup` and stay registered for the lifetime of the integration, as the Home Assistant
  integration quality scale requires (rule `action-setup`). Automations and scripts that call
  them then validate even when no device is loaded, and a call that targets no loaded device
  already raises `ServiceValidationError`. This removes the per-entry registration the issue
  points at, and with it the order dependency on the first entry.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Options can be saved when a scheduler disappeared (Priority: P1)

A user who removed or renamed a scheduler can still change any option of the device.

**Why this priority**: The options form is the only way to edit a device; today it is blocked.

**Independent Test**: Configure a device with `switch.schedule_gone`, which has no state, open
the options and submit them unchanged.

**Acceptance Scenarios**:

1. **Given** a device configured with an existing scheduler and `switch.schedule_gone`, which no
   longer exists, **When** the options form opens, **Then** `switch.schedule_gone` is one of the
   scheduler options, labelled as not found.
2. **Given** that form, **When** it is submitted unchanged, **Then** the options are saved.
3. **Given** that form, **When** `switch.schedule_gone` is unselected and the form submitted,
   **Then** only the existing scheduler is saved.

### User Story 2 — A VTherm is driven by one device only (Priority: P1)

**Why this priority**: Two devices driving one VTherm overwrite each other's setpoint.

**Acceptance Scenarios**:

1. **Given** a device named "Intelligent Heating Pilot" on `climate.bedroom`, **When** a second
   device with the same name is set up on `climate.office`, **Then** it is created, with the
   `unique_id` `climate.office`.
2. **Given** a device on `climate.bedroom`, **When** a device is set up on `climate.bedroom`
   under another name, **Then** the setup aborts with `already_configured`.
3. **Given** a device whose options moved it to `climate.bedroom`, **When** a device is set up on
   `climate.bedroom`, **Then** the setup aborts with `already_configured`.
4. **Given** devices on `climate.bedroom` and `climate.office`, **When** the options of the
   second are changed to `climate.bedroom`, **Then** the form shows
   `vtherm_already_configured` on the VTherm field and nothing is saved.
5. **Given** a device, **When** its options are saved with its own VTherm, **Then** they are
   saved.
6. **Given** a device on `climate.office`, **When** its options move it to `climate.study`,
   **Then** its `unique_id` becomes `climate.study`.

### User Story 3 — Unloading a device leaves nothing behind (Priority: P2)

**Acceptance Scenarios**:

1. **Given** Home Assistant still starting, **When** a device is set up then unloaded before
   `EVENT_HOMEASSISTANT_STARTED`, **Then** the event schedules no startup work for it.
2. **Given** Home Assistant still starting, **When** a device is set up and the event fires,
   **Then** its startup work is scheduled once.
3. **Given** Home Assistant already started, **When** a device is set up, **Then** its startup
   work is scheduled at once.
4. **Given** a loaded device, **When** its platforms fail to unload, **Then** the unload reports
   failure, the coordinator is not cleaned up and stays in `hass.data`.
5. **Given** a loaded device, **When** it is unloaded, **Then** its platforms are unloaded before
   its coordinator is cleaned up, and the coordinator leaves `hass.data`.

### User Story 4 — Services exist with or without devices (Priority: P2)

**Acceptance Scenarios**:

1. **Given** the integration set up, **When** no device is loaded, **Then** `reset_learning` and
   `calculate_anticipated_start_time` are registered.
2. **Given** the last device unloaded, **When** `reset_learning` is called for one of its
   entities, **Then** it raises `ServiceValidationError`.
3. **Given** two devices, **When** `reset_learning` targets one, **Then** only that one is reset
   (unchanged behaviour).

### Edge Cases

- A scheduler configured as a plain string (older entries) is handled like a one-item list.
- A device with no scheduler shows the scheduler options of the existing entities only.
- When no scheduler entity is found, the form keeps its entity picker, as today: it accepts any
  `switch` or `schedule` entity, so a configured scheduler without a state does not block it.
- The VTherm duplicate check ignores the device being edited.
- An options entry that clears a field (stored as `None`) falls back to the setup value, as
  `HADeviceConfigReader` does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the forms offer a dropdown of the schedulers found, it MUST include every
  configured scheduler, those without a state labelled as not found.
- **FR-002**: The setup form MUST abort with `already_configured` when the VTherm in use by another
  device is the one selected, and MUST NOT abort on a shared name.
- **FR-003**: A new device MUST take its VTherm entity id as `unique_id`.
- **FR-004**: The options form MUST refuse a VTherm in use by another device with the
  `vtherm_already_configured` error, and MUST update the `unique_id` when the VTherm changes.
- **FR-005**: The startup listener MUST be cancelled when the entry unloads.
- **FR-006**: The manifest MUST declare `http` and `recorder` as dependencies.
- **FR-007**: `async_unload_entry` MUST unload the platforms first, and clean up and forget the
  coordinator only when that succeeds.
- **FR-008**: Services MUST be registered once, in `async_setup`.
- **FR-009**: Every new error and abort text MUST exist in `strings.json`, `en.json` and
  `fr.json`.

## Success Criteria *(mandatory)*

- **SC-001**: The options of a device whose scheduler was removed can be saved without first
  clearing the scheduler field.
- **SC-002**: The existing config-flow, setup, service and translation tests pass, adapted only
  where they relied on per-entry service registration or on the error list.

## Plan

- `config_flow.py`:
  - `_scheduler_selector(hass, configured)` builds the scheduler field shared by both forms:
    the dropdown of the schedulers found plus the configured ones, or the entity picker when
    none is found.
  - `_configured_vtherm(entry)` returns the VTherm in use (options, else data).
  - `_vtherm_in_use(hass, vtherm, exclude_entry_id)` finds another entry using that VTherm.
  - User step: abort on a VTherm in use, `unique_id` = VTherm.
  - Options step: error on a VTherm in use, update the `unique_id` when the VTherm changes.
- `services.py` (new): `async_setup_services(hass)` registers both services; the handlers move
  out of `async_setup_entry` unchanged.
- `__init__.py`:
  - Call `async_setup_services` from `async_setup`.
  - Use `async_at_started` wrapped in `entry.async_on_unload`.
  - Reorder `async_unload_entry`.
- `manifest.json`: `"dependencies": ["http", "recorder"]`.
- `strings.json`, `translations/en.json`, `translations/fr.json`: new abort text, new options
  error.

## Tasks

1. design: this specification.
2. test: integration tests for the options with a missing scheduler, the VTherm uniqueness, the
   start listener, the unload order and the service registration; translation test adapted to
   the new options error.
3. fix: config flow, setup and unload, manifest, translations.
4. docs: CHANGELOG `[Unreleased]` entry.
