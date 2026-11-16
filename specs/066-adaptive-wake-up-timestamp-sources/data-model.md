# Data Model: Adaptive wake-up from timestamp sources

All new value objects are `@dataclass(frozen=True)` in `domain/value_objects`.

## WakeUpSourceConfig (new)

| Field | Type | Rule |
| --- | --- | --- |
| `entity_id` | `str` | not blank; unique within one IHP |
| `fixed_target` | `SlotAction \| None` | a preset or a temperature (existing value object) |
| `target_from_schedule` | `bool` | default `False` |
| `horizon` | `timedelta` | default 24 h; positive |
| `hold` | `timedelta \| None` | absent by default; positive when set |

Invariant (FR-007): `fixed_target is not None or target_from_schedule`. "From schedule" is honored only when the IHP has a scheduler; otherwise `fixed_target` is required, checked at configuration time and again when read.

## WakeUpReading (new)

The raw reading of a source: `value: datetime | None` (timezone-aware) and `reason: ReadingIssue | None` (`UNKNOWN`, `UNAVAILABLE`, `NOT_A_FULL_DATETIME`, `UNPARSABLE`) for logging once per change. Built by the adapter; judged by `WakeUpDeadlinePolicy`.

## SlotsAround (new)

`in_effect: ScheduledTimeslot | None`, `following: ScheduledTimeslot | None` for one scheduler and one moment. Either may be absent; both absent means "the scheduler cannot say".

## ScheduledTimeslot (extended)

Adds `hold: timedelta | None = None`. Default keeps every existing slot as is. A source slot carries `scheduler_entity` = the source entity id, `timeslot_id` = `<entity>_<local date of the deadline>` (stable across a snooze), and `action` = the resolved target.

## PreheatRecord (extended)

Adds `hold_until: datetime | None = None` (aware when set) and `hold_handoff: bool = False`. Stored records without the fields load with the defaults.

## SchedulerKind (extended)

Adds `TIMESTAMP = "timestamp"`.

## Rules (domain services)

- **WakeUpDeadlinePolicy.judge(reading, now, horizon)** returns the deadline or nothing: nothing when the value is absent, not after `now`, or more than `horizon` ahead.
- **WakeUpTargetPolicy.resolve(config, slots, reference_target)** returns the `SlotAction` or nothing:
  1. not `target_from_schedule`: the fixed target;
  2. both slots known: the one with the higher temperature (a preset compared through its published temperature);
  3. one slot known: it, only if its temperature is higher than `reference_target`;
  4. otherwise the fixed target, or nothing (source ignored).
  `reference_target` is the recorded pre-preheat target when a record exists for the deadline, else the live one.
- **Deadline choice**: earliest valid deadline across schedulers and sources; at the same instant the scheduler slot wins.
- **PreheatSessionPolicy.decide_hold_end(record, snapshot)**: `DISCARD` when `record.hold_handoff` (a scheduler slot bounded the hold), `LEAVE` when climate unavailable, off or changed by someone else, `RESTORE` otherwise.

## State transitions of a source preheat

`idle` → (valid deadline, start reached) `preheating` → (deadline reached, no hold) `idle`; → (deadline reached, hold) `holding` → (timer, untouched) `restored` / (changed or scheduler slot first) `idle`. From `preheating`: deadline moved → stays `preheating` on the new deadline; closer deadline → handover; deadline removed → cancel and restore.
