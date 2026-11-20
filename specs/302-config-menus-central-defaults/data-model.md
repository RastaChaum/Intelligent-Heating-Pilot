# Data Model: Configuration menus and central default configuration

All domain types are immutable (`@dataclass(frozen=True)`) and validate in `__post_init__`.
Names are in English; every field has a type hint.

## SettingScope (enum)

`DEVICE` (never inherited) or `SHAREABLE` (can be inherited from the central configuration).

## SettingTheme (enum)

`THERMOSTAT_SCHEDULERS`, `NATIVE_SCHEDULE`, `WAKE_UP_SOURCES`, `ENVIRONMENT`, `LEARNING`,
`CYCLE_DETECTION`, `ANTICIPATION`.

## SettingDefinition

One declared setting.

| Field | Type | Rule |
|-------|------|------|
| `key` | `str` | non-empty, unique in the catalog, equal to the stored key |
| `theme` | `SettingTheme` | the form it appears in |
| `scope` | `SettingScope` | `DEVICE` or `SHAREABLE` |
| `default` | `object \| None` | the built-in default; `None` for optional entities |
| `optional` | `bool` | true when "none" is a valid value (environment sensors) |

- A `DEVICE` setting never has `optional` set for inheritance purposes; the flag only drives the
  clear-to-none behavior of its own form.
- The catalog holds the definitions; bounds and selectors stay in infrastructure, which maps a key
  to a Home Assistant selector.

## SettingSource (enum)

`OVERRIDE` (device holds the key), `CENTRAL` (central holds the key), `DEFAULT` (built-in).

## ResolvedSetting

| Field | Type | Rule |
|-------|------|------|
| `key` | `str` | a catalog key |
| `value` | `object \| None` | the effective value; `None` is "none" |
| `source` | `SettingSource` | where the value came from |

## SettingsResolver (service, stateless)

`resolve(catalog, device_values, central_values) -> Mapping[str, ResolvedSetting]`

For each catalog entry:

1. if `device_values` holds the key: `OVERRIDE`, even when the value is `None` or equals the
   central one;
2. else if the scope is `SHAREABLE` and `central_values` holds the key: `CENTRAL`;
3. else: `DEFAULT`.

A `DEVICE` setting is never read from `central_values`, even if the central mapping holds the key
(a defensive rule: FR-008).

## Stored shape (config entries)

| Entry | Where | Content |
|-------|-------|---------|
| Device | `data` | `name`, `vtherm_entity_id`, `scheduler_entities`; legacy entries also hold the shareable keys they were created with |
| Device | `options` | device-only keys, overrides (key present), `None` for an explicit "none" |
| Central | `data` | `entry_type: "central"` |
| Central | `options` | shareable keys that have a central value; an absent key means no central value |

## State transitions of one shareable setting on a device

```text
absent (inherit) --user selects it and saves--> present (override)
present (override) --user unselects it and saves--> absent (inherit)
present (override) --user clears an optional entity--> None ("none")
None ("none") --user unselects it and saves--> absent (inherit)
```

## Validation rules

- Bounds and types per setting are the ones of the current forms (FR-005); they live in the
  selector mapping and are applied by the device theme forms and the central theme forms alike.
- The central entry rejects the same out-of-range values as a device (edge case in the spec).
- Device-only keys are never written to the central entry.
