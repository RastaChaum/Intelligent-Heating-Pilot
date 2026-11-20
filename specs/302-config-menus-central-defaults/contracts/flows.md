# Flow Contracts: Configuration menus and central default configuration

The UI contract of the feature: steps, what each shows, and where it leads. Step ids are also the
translation keys under `options.step`.

## Device options flow

```text
init (menu)
├── thermostat_schedulers   -> form: vtherm, schedulers (save stores)         -> init
├── native_schedule         -> form: drive + overrides picker                -> native_schedule_values -> init
├── wake_up_menu            -> existing wake-up sources flow (unchanged)     -> init
├── environment             -> form: indoor humidity + overrides picker      -> environment_values -> init
├── learning                -> form: overrides picker                        -> learning_values -> init
├── cycle_detection         -> form: overrides picker                        -> cycle_detection_values -> init
├── anticipation            -> form: overrides picker                        -> anticipation_values -> init
└── apply                   -> offered only while stored changes are unapplied (or the entry is not loaded): reload once, finish
```

- Each `<theme>` step shows, in its description, one line per shareable setting: "inherited
  (value)" or "overridden (value)".
- The overrides picker is a multi-select of the theme's shareable settings, pre-selected with the
  ones the device overrides. An empty selection skips the `_values` step.
- The `_values` step shows only the selected settings, pre-filled with their effective value. A
  cleared optional entity is stored as `None`.
- Unselecting a setting removes its key from the stored data and options (inherit).
- Validation errors keep the step open with the error on the field; nothing is stored.
- `init` description says how many themes have unapplied changes. `apply` is not listed when
  nothing is unapplied. Closing the dialog loses nothing.

## Central options flow

```text
init (menu)
├── environment      -> form: outdoor temperature, outdoor humidity, cloud coverage
├── learning         -> form: auto learning, dead time, retention, extraction range
├── cycle_detection  -> form: delta, min, max, split, safety grace
├── native_schedule  -> form: preset key, temperature key, fallback preset
├── anticipation     -> form: recalculation tolerance
└── apply            -> offered only while stored central values are unapplied: reloads the
                        inheriting devices once, finish
```

- Fields are shown directly; no picker. A cleared field removes the key (no central value).
- No device-specific field and no wake-up entry.

## Creation flow

- `user` step (PR2): name, thermostat, schedulers. Stores no shareable key (FR-022).
- `import` step: used only by `ensure_central_entry`; creates the central entry with
  `entry_type: "central"`, the fixed unique id and empty options; aborts when it exists.

## Translation keys to provide (en, fr, strings.json)

`options.step.init.menu_options.*`, `options.step.<theme>.{title,description,data,data_description}`,
`options.step.<theme>_values.{title,description,data,data_description}`, the inherited and
overridden indicator texts, the menu description about unapplied themes, and the central entry
title and description. A unit test walks the catalog and fails on any missing key in the three
files.
