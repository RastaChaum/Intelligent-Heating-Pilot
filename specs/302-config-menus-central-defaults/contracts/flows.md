# Flow Contracts: Configuration menus and central default configuration

The UI contract of the feature: steps, what each shows, and where it leads. Step ids are also the
translation keys under `options.step`.

## Device options flow

```text
init (menu)
├── thermostat_schedulers   -> form: vtherm, schedulers (save stores)         -> init
├── native_schedule         -> form: drive + a toggle per shared key          -> init
├── wake_up_menu            -> existing wake-up sources flow (unchanged)     -> init
├── environment             -> form: indoor humidity + a toggle per sensor   -> init
├── learning                -> form: a toggle per setting                    -> init
├── cycle_detection         -> form: a toggle per setting                    -> init
├── anticipation            -> form: a toggle per setting                    -> init
└── apply                   -> offered only while stored changes are unapplied (or the entry is not loaded): reload once, finish
```

- Each shareable setting is an "Inherited / Custom" toggle (Home Assistant's choose selector,
  hence Home Assistant 2026.2 or later). It opens on "Custom" when the device stores the key,
  else on "Inherited".
- "Inherited" shows the inherited value (central, else built-in default) as text: a sensor by its
  friendly name, a switch as on/off, an empty sensor as "none". It cannot be edited.
- "Custom" shows the setting's usual selector, starting from the effective value. A custom
  optional entity left empty is stored as `None` (no sensor); a custom number left empty is
  rejected.
- Submitting "Inherited" removes the key from the stored data and options. Toggles left as they
  opened store nothing.
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
`selector.inheritance.choices.{inherited,custom}`, `common.{none,on,off}`, the menu description about unapplied themes, and the central entry
title and description. A unit test walks the catalog and fails on any missing key in the three
files.
