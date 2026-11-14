# Data Model: Drive the climate at the anticipated start

All domain types are immutable (`@dataclass(frozen=True)`) and validate in `__post_init__`.
Names are in English; fields have type hints.

## SlotAction

What a slot asks of the climate.

| Field | Type | Rule |
|-------|------|------|
| `preset` | `str \| None` | non-empty when set |
| `temperature` | `float \| None` | finite when set |

- At least one field is set, otherwise `ValueError`.
- `applied_kind` is `PRESET` when a preset is set (preset wins), else `TEMPERATURE`.
- `calculation_temperature` is the temperature when set; otherwise unresolved here (the reader
  resolves a preset to a temperature for the calculation, as today).

## ScheduledTimeslot (existing, extended)

New field: `action: SlotAction | None = None`. `None` means the scheduler gives no usable action
(HACS path, unsupported kind, "no change" node). `target_time` already carries its date, so a
slot after midnight keeps its own day. `target_temp` stays: the anticipation needs it.

## ClimateSnapshot

The climate's requested state at one moment.

| Field | Type | Note |
|-------|------|------|
| `hvac_mode` | `str` | `off` means the user stopped the climate |
| `preset` | `str \| None` | requested preset |
| `temperature` | `float \| None` | requested target temperature |
| `available_presets` | `tuple[str, ...]` | to check a preset is offered |

## PreheatRecord

| Field | Type | Note |
|-------|------|------|
| `timeslot_id` | `str` | identity of the slot, already built by the readers |
| `scheduler_entity` | `str` | owner of the slot |
| `slot_time` | `datetime` | timezone-aware |
| `previous` | `ClimateSnapshot` | state before IHP acted |
| `applied` | `SlotAction` | what IHP applied |
| `recorded_at` | `datetime` | timezone-aware |

One record exists per IHP instance; a new one is saved only after the previous one is cleared.
Lifecycle: created once before the first command of a slot; removed on completion (slot time),
on restore, on leave, on discard. Never replaced while the slot is the same.

## SchedulerKind (enum)

`HACS`, `NATIVE`, `CLIMATE_SCHEDULER`, `UNKNOWN`.

## ActuationResult (enum)

`ATTEMPTED` (sent, effect not verified by the actuator: HACS), `APPLIED` (sent and confirmed),
`NOT_APPLIED` (sent or refused, no effect: logged once per slot at INFO), `SKIPPED` (a guard
stopped it, such as a climate that is off: retried silently, DEBUG only), `UNSUPPORTED`
(nothing sent, by design).

## PreheatStartOutcome (enum, application level)

`STARTED`, `UNSUPPORTED`, `BLOCKED`, `RETRY`. Mapping from `ActuationResult`:
`ATTEMPTED` is verified by the use case as today and becomes `STARTED` or `BLOCKED`;
`APPLIED` becomes `STARTED`; `NOT_APPLIED` and `SKIPPED` become `RETRY` (only `NOT_APPLIED` logs at INFO); `UNSUPPORTED` becomes `UNSUPPORTED`
(treated as today's compute-only success, so existing sensors and completion logic are unchanged).

## RestoreDecision (enum)

`RESTORE`, `LEAVE`, `DISCARD`.

## CancelReason (enum)

`SLOT_CHANGED`, `SCHEDULER_DISABLED`, `IHP_DISABLED`, `POSTPONED`, `SLOT_REACHED` (the slot
time arrived: the record is discarded, nothing is restored, and a delegated preheat sends nothing).

## RestoreFields

Frozen value `preset | None`, `temperature | None`, with `is_empty`. It carries only what IHP
writes back to the climate.

## Constants

`PREHEAT_RESTORE_GUARD_MINUTES = 5` (domain constants): within this delay of the slot, a
cancellation is a completion, because the scheduler is about to apply the same action.

## Policy rules (PreheatSessionPolicy)

- `decide_apply(snapshot, action)`: skip when `hvac_mode == "off"`; skip when a preset is
  requested and not in `available_presets`; skip when the snapshot already equals the action.
- `restore_fields(record)`: the previous preset when there was a real one (not absent, not
  `none`), whatever IHP applied, because a temperature slot takes a thermostat off its preset
  and the setpoint follows the preset once it is back; otherwise the previous temperature.
  The HVAC mode is never restored.
- `decide_restore(record, snapshot, now)`: `DISCARD` if `slot_time - now` is within the guard
  window or negative; `LEAVE` if the snapshot differs from `record.applied`; else `RESTORE`.
- `is_claimed_by_other(record, snapshot)`: the snapshot differs from `record.applied`.
