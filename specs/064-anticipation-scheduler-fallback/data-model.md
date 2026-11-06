# Data Model: Anticipation Falls Back When a Scheduler's Conditions Block It

**Feature**: [spec.md](./spec.md) | **Date**: 2026-10-26

No new persisted entity or storage schema is introduced. This feature only changes how
existing data flows and adds one ephemeral, call-scoped value.

## Existing entity reused unchanged

### `ScheduledTimeslot` (`domain/value_objects/scheduled_timeslot.py`)

Already `@dataclass(frozen=True)`: `target_time`, `target_temp`, `timeslot_id`,
`scheduler_entity`. This feature needs *several* of these per recalculation (one per
candidate scheduler, obtained one at a time via repeated calls with a growing exclusion set)
— no shape change required.

## New ephemeral value (not persisted, not a domain entity)

### Exclusion set — `frozenset[str]` of scheduler entity ids

- **Lifetime**: a single call to `HeatingOrchestrator.calculate_and_schedule_anticipation()`
  (one recalculation cycle). Built up locally as candidates are confirmed blocked; discarded
  when the call returns.
- **Not stored** on any use case, adapter, or persisted structure — satisfies the Stateless
  Service constitution gate and the user's resolution that exclusion is cycle-scoped only
  (FR-004a). The *next* periodic recalculation starts from an empty set, giving the earliest
  scheduler a fresh chance.
- **Bounded**: cannot exceed the number of scheduler entities configured for the device (a
  small, user-configured list), so the retry loop built on it always terminates.

## Changed data flow: `anticipation_data` dict

`CalculateAnticipationUseCase._create_data_structure()` and the sensors reading it
(`sensor.py`) already pass a plain `dict` end to end. Two keys are added, both already
reachable from existing `extra_state_attributes` plumbing:

| Key | Type | Meaning |
| --- | --- | --- |
| `scheduler_blocked` | `bool` | `True` only when every configured scheduler was confirmed blocked this cycle (FR-004) and no heating action could be delivered. Defaults to `False`. |
| `blocked_schedulers` | `list[str]` | Entity ids confirmed blocked this cycle, in attempt order. Empty list when `scheduler_blocked` is `False`. Diagnostic detail, not required by any acceptance scenario but costs nothing extra once the exclusion set already exists. |

No existing key's meaning or type changes — single-scheduler and native-schedule households
(User Stories 2, 3) see `scheduler_blocked: False`, `blocked_schedulers: []` added but
nothing else different.

## State transitions

```text
[recalculation starts] --excluded={}--> try earliest candidate
        |
        v
  run_action + verify ---- confirmed OK ----> schedule/trigger normally; done (excluded discarded)
        |
    confirmed blocked
        |
        v
  excluded += {entity}; any candidate left (scheduler_reader.get_next_timeslot(exclude_entity_ids=excluded))?
        |                                   \
       yes                                   no
        |                                     |
        v                                     v
  try next candidate (loop)          scheduler_blocked=True, blocked_schedulers=excluded,
                                      WARNING log; stop for this cycle
```

Unreadable VTherm state after `run_action` is treated as "confirmed OK" for the purpose of
this diagram (per the resolved clarification) — it never enters the "confirmed blocked"
branch.

**Invariant**: `ControlPreheatingUseCase`'s own state (`is_preheating_active`,
`preheating_target_time`, `active_scheduler_entity`) is mutated only on the "confirmed OK"
branch. A "confirmed blocked" outcome leaves that state untouched, so the very next call in
the same cycle (trying the fallback candidate) is not blocked by a stale "already
preheating" guard.
