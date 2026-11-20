# Research: Configuration menus and central default configuration

Format: Decision, Rationale, Alternatives considered. Findings about the current code were read
from `config_flow.py`, `config_flow_wake_up.py`, `__init__.py`, `device_config_reader.py` and
`const.py`. Findings about Home Assistant behavior marked "verify" are checked by task T0.

## D1. How an override is represented

**Decision**: a shareable key present in a device entry's data or options is an override; an
absent key inherits. `None` stored in the options is the explicit "none" of an optional entity.

**Rationale**: the current reader already applies "options override data" and already treats `None`
in options as "deleted, do not fall back" (`_opt_or_data`). Presence-based override needs no
migration: every value an existing device holds is already an override (FR-012), and no marker
field has to be kept in sync with the values.

**Consequence**: a legacy entry may hold shareable keys in `data`. Resetting such a key to
"inherit" must remove it from `data` and `options` in one `async_update_entry` call, because an
absent options key falls back to `data`.

**Alternatives**: a per-device list of overridden keys (rejected: second source of truth, needs a
migration); storing the inheritance mode per key (rejected: same, plus larger entries).

## D2. How the central configuration is stored

**Decision**: a config entry of the same domain, `data = {"entry_type": "central"}`, unique id
`central_configuration`, values in its options. Devices read it through `ICentralConfigReader`,
which looks it up with `async_entries(DOMAIN)` and does not depend on it being loaded.

**Rationale**: the issue notes that one config entry per flow handler is the default and suggests
a dedicated entry type. A visible entry gives the "Configure" button the spec asks for (FR-023)
and survives restarts with no custom storage. Reading the entry directly avoids a load-order
dependency between the central entry and the devices.

**Alternatives**: a `Store` plus a services-only editor (rejected: no UI entry point); a "central"
flag on one of the devices (rejected: ties shared values to one device's lifecycle); a separate
integration domain (rejected: heavier install, two repositories).

## D3. Device creation

**Decision**: from PR2, the creation step asks only for name, thermostat and schedulers, and stores
only those keys.

**Rationale**: FR-022. Storing the other keys would turn each into an override.

**Alternatives**: keep the full form pre-filled and diff against the central values (rejected by the
user: Q1 option A).

## D4. Showing inherit, override and reset in a form

**Decision**: per theme, a multi-select of overridden settings plus a second form with only the
selected ones; descriptions list "inherited (value)" or "overridden (value)".

**Rationale**: Home Assistant forms have no tri-state field. A companion checkbox per field would
double the fields and break the 8 field limit (SC-001). The multi-select is one extra field per
theme and makes reset one click.

**Alternatives**: a checkbox next to each field (rejected: doubles fields); a free-text sentinel
such as "inherit" in each field (rejected: breaks typed selectors); a separate "reset" menu
(rejected: hides the state the user wants to see, SC-004).

## D5. When values are persisted

**Decision**: each theme form stages its values in memory; an "Apply" entry on the main menu,
offered only while something is staged, persists once and reloads once. Closing the dialog
discards staged values.

**Rationale**: persisting updates the entry, and the entry update listener reloads the device (or,
for the central entry, the inheriting devices). Persisting per theme would reload per theme, which
Q4 rules out. The wake-up flow already stages the same way.

**Platform limits**: a menu cannot grey an entry out, so "Apply" is omitted when nothing is
staged; the frontend gives an integration no hook on the close button, so the unapplied warning is
text in the menu description (verify in T0).

**Alternatives**: persist per theme (rejected: repeated reloads); a debounce on the listener
(rejected: timing logic and flaky tests for no user gain).

## D6. Propagating a central change

**Decision**: the central entry's update listener diffs the new options against the snapshot taken
at load and reloads each device entry that holds none of the changed keys.

**Rationale**: matches FR-009 and Q4 exactly, uses the standard entry reload, and needs no new
event (FR-018: the update listener is the announcement of a changed entry).

**Alternatives**: an IHP event consumed by each device (rejected: extra moving part, the entry
listener already exists); reload every device (rejected by Q4).

## D7. Upgrade without rewriting entries

**Decision**: no migration step. Existing entries stay as they are.

**Rationale**: D1 makes every held value an override. The new central entry starts empty, so
nothing changes until the user sets a central value (SC-003). A config entry version bump would
add risk for no benefit.

**Alternatives**: write every default into each device (rejected: creates overrides the user never
chose and defeats inheriting).

## D8. Deleting the central entry (verify)

**Decision**: implement the spec fallback. When no central entry exists, devices use built-in
defaults. `ensure_central_entry` recreates it at the next device setup (which also runs at startup).
A WARNING is logged when a central entry is removed while devices exist.

**Rationale**: as far as the current Home Assistant API goes, `async_remove_entry` is called after
the entry has been removed and cannot return a refusal. Task T0 verifies this on the pinned
version before PR2 starts. If a veto exists, the refusal replaces the fallback and this decision
is revised.

**Alternatives**: hide the delete button (rejected: not available to integrations); a repair issue
asking the user to restore it (rejected: more UI for a rare case; the entry is recreated anyway).

## D9. Which settings are shareable

**Decision**: shareable: outdoor temperature, outdoor humidity, cloud coverage, auto learning,
initial dead time, data retention, recorder extraction range, the four cycle detection values,
safety grace period, recalculation tolerance, native schedule preset key, temperature key and
fallback preset. Device-only: name, thermostat, schedulers, wake-up sources, native schedule
drive (Q1), indoor humidity, the IHP enabled switch.

**Rationale**: the issue lists environment sensors, learning and cycle parameters, safety grace
period and native schedule keys. Indoor humidity belongs to the room of one device, not to the
installation, so it is not inherited. The initial dead time is shareable as the issue lists it; its
learned value still lives per device.

**Alternatives**: share indoor humidity (rejected: wrong for rooms with different sensors).

## D10. Splitting the flow module

**Decision**: `config_flow.py` keeps only entry points; theme steps and selector building move to
two modules shared by the device and central flows.

**Rationale**: the creation form and the options form currently repeat the same 15 selectors
(about 700 lines). Deriving them from the catalog keeps one definition and meets the rule of
removing duplicate code paths rather than adding a third copy for the central entry.

**Alternatives**: a third copy for the central flow (rejected: drift, the problem the feature
exists to remove).

## D11. Translations

**Decision**: every theme title, menu entry, field label, field help, picker label and indicator
text is added to `strings.json`, `en.json` and `fr.json`; the existing parity tests are extended to
walk the catalog.

**Rationale**: FR-015 and #193. Deriving the expected keys from the catalog stops a new setting
from shipping without labels.

**Alternatives**: spot checks of a few keys (rejected: misses new settings).
