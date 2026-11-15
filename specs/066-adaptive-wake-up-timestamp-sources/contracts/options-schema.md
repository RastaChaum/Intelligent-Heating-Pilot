# Contract: wake-up source options

Stored in the config entry options under `wake_up_sources`: a list of objects.

| Key | Type | Required | Default |
| --- | --- | --- | --- |
| `entity_id` | entity (sensor timestamp, datetime, input_datetime) | yes | |
| `target_from_schedule` | bool | no | false |
| `target_preset` | string | one of preset or temperature, when not from schedule alone | |
| `target_temperature` | number | idem | |
| `horizon_hours` | number, 1 to 72 | no | 24 |
| `hold_minutes` | number, 0 to 720 | no | absent (0 is absent) |

Rules: an entity appears once per IHP; a source needs a fixed target unless `target_from_schedule` is true and a scheduler is configured; preset wins when both fixed values are given (same rule as `SlotAction`).

Options flow: a menu step with add, edit, remove, done; one form per source. Every label, description and error is in `strings.json`, `translations/en.json` and `translations/fr.json`, with the three files in key parity.
