---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Every Setting and Service Has a Readable Label in English and French

**Feature Branch**: `fix/issue-193-translations-sync`
**Created**: 2026-10-31
**Status**: Draft
**Input**: GitHub issue #193 — "Translations incomplete and out of sync with the config flow"

## Context

Home Assistant shows the labels and help texts of a custom integration's setup form, options
form and services from `translations/<language>.json`. When a key is missing in the user's
language, it falls back to English; when it is missing in English too, the form shows the raw
key (`auto_learning`, `dead_time_minutes`, …).

The three text files of IHP have drifted apart from the forms and from each other:

- `translations/en.json` has no label for 7 of the 17 setup fields (`auto_learning`,
  `dead_time_minutes`, `temp_delta_threshold`, `cycle_split_duration_minutes`,
  `min_cycle_duration_minutes`, `max_cycle_duration_minutes`,
  `safety_shutoff_grace_minutes`), in both the setup and the options form. English users see
  raw keys.
- `translations/fr.json` misses the same labels in the setup form, plus
  `task_range_days`; its options form misses `auto_learning` and `dead_time_minutes`.
- Neither translation declares the `required` error, so leaving the thermostat empty shows the
  raw `required` key instead of a message.
- `strings.json` (the source file of the English text) misses `auto_learning`,
  `dead_time_minutes` and `anticipation_recalc_tolerance_minutes`, and its texts differ from
  `en.json`.
- `cannot_connect`, `invalid_auth` and `unknown` errors are declared but never raised.
- The safety shutoff grace period is the only duration field without a unit.
- The two services (`calculate_anticipated_start_time`, `reset_learning`) have no
  `services` section, so they are never shown in French.

Nothing prevents the drift from coming back: no test compares the text files with the forms.

## Clarifications

### Session 2026-10-31

- Q: Which file is the source of truth for English? → A: `translations/en.json`, because
  it is the one Home Assistant loads for a custom integration. `strings.json` is kept as an
  identical copy (the Home Assistant convention for core integrations), and a test enforces
  the copy.
- Q: Must every field also have a help text, or only a label? → A: Both, in both forms and
  both languages. The options form currently shows help for 6 of its 16 fields; the same help
  is useful when changing a setting as when setting it first.
- Q: Should the service names and descriptions move out of `services.yaml`? → A: No. Service
  translations need Home Assistant 2023.8, while `hacs.json` declares 2023.1 as the minimum.
  `services.yaml` keeps its English texts as the fallback for older versions; the translation
  files add the `services` section on top.
- Q: The issue only lists `cannot_connect` and `invalid_auth` as unused. What about
  `unknown`? → A: It is never raised either, so it is removed too. The declared errors are
  exactly those the forms can show.
- Q: The documentation calls the dead time field "Initial Dead Time" and the learning switch
  "Automatic Learning". Which names do the forms use? → A: The documentation names, so a user
  can match the form with `docs/users/CONFIGURATION.md`. The help texts describe the actual
  behavior: automatic learning only governs the dead time (the heating slope is always
  learned), which the documentation misstated.
- Q: The scheduler field still says "switches", although native `schedule.*` helpers are
  accepted since #188. Fix it here? → A: Yes, it is text in the same files: the label drops
  "(switches)" and the help text mentions native schedules and their limit (anticipation only,
  no automatic start).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Every setting shows a label and a help text (Priority: P1)

A user adds an IHP device, or opens its options, in English or French. Every field shows a
human-readable label and a help text in their language.

**Why this priority**: This is the defect of issue #193. Seven settings currently show raw
keys in English, which makes the form hard to use.

**Independent Test**: Open the setup and the options forms and compare their fields with the
labels and help texts declared in each translation file.

**Acceptance Scenarios**:

1. **Given** the setup form, **When** it is shown in English or French, **Then** each of its
   fields has a label and a help text in that language.
2. **Given** the options form, **When** it is shown in English or French, **Then** each of its
   fields has a label and a help text in that language.
3. **Given** a translation file, **When** it is compared with the forms, **Then** it declares
   no label or help text for a field the form does not have.

### User Story 2 — A validation error shows a message (Priority: P1)

A user submits the setup or options form without a thermostat. The form shows "This field is
required" (or its French translation), not the raw `required` key.

**Independent Test**: Submit each form without a thermostat and check that the error raised
is declared in each translation file.

**Acceptance Scenarios**:

1. **Given** the setup form submitted without a thermostat, **When** the error is shown,
   **Then** its message is declared in English and French.
2. **Given** the options form submitted without a thermostat, **When** the error is shown,
   **Then** its message is declared in English and French.

### User Story 3 — Services are described in the user's language (Priority: P2)

A user opens an IHP service in the Developer tools or an automation editor. Its name, its
description and its fields are shown in their language.

**Independent Test**: Compare the services and fields of `services.yaml` with the `services`
section of each translation file.

**Acceptance Scenarios**:

1. **Given** a service declared in `services.yaml`, **When** it is shown in English or
   French, **Then** its name, description and each field's name and description are
   translated.

### Edge Cases

- **A new field added to a form without translations**: the test suite fails and names the
  missing key, for each language and each form.
- **A field removed from a form**: the test suite fails on the leftover translation.
- **French translation drifting from English**: both files must declare the same keys; the
  test reports the keys present in one only.
- **Home Assistant older than 2023.8**: the service texts from `services.yaml` are still
  shown, in English.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each translation file MUST declare a label (`data`) and a help text
  (`data_description`) for every field of the setup form (`config.step.user`) and of the
  options form (`options.step.init`), and for no other field.
- **FR-002**: Each translation file MUST declare, under `config.error` and `options.error`,
  exactly the errors the corresponding form can raise (today: `required`).
- **FR-003**: `translations/fr.json` MUST declare the same keys as `translations/en.json`.
- **FR-004**: `strings.json` MUST be identical to `translations/en.json`.
- **FR-005**: Each translation file MUST declare a `services` section giving, for every
  service and every field of `services.yaml`, a `name` and a `description`.
- **FR-006**: Every numeric field of both forms MUST declare a unit of measurement; the safety
  shutoff grace period MUST use `minutes`.
- **FR-007**: The form labels MUST use the setting names of
  `docs/users/CONFIGURATION.md`.

### Key Entities

- **Form field**: a key of the setup or options form schema; it is the reference the
  translation files are checked against.
- **Translation file**: `strings.json`, `translations/en.json`, `translations/fr.json`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 raw keys shown in the setup form, the options form and the services, in
  English and French (today: 7 raw keys per English form).
- **SC-002**: Adding or removing a form field without updating the three text files fails at
  least one test.
- **SC-003**: No behavior change: the saved configuration and the services are unchanged.

## Assumptions

- Home Assistant falls back to English for a key missing in the user's language, and shows
  the raw key when English misses it too.
- `services.yaml` texts are only a fallback once a `services` translation exists.

## Out of Scope

- Entity names and states (sensors, switch): their names are set in code, not translated.
- Exception messages raised by the services.
