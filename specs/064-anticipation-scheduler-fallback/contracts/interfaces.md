# Interface Contracts: Anticipation Falls Back When a Scheduler's Conditions Block It

**Feature**: [spec.md](./spec.md) | **Date**: 2026-10-26

Method bodies below are stubs/signatures only — the implementation happens in
`/speckit.implement`. All are additions or signature changes to interfaces that already
exist in `domain/interfaces/`.

## 1. `IClimateDataReader` — new method

File: `domain/interfaces/climate_data_reader_interface.py`

```python
@abstractmethod
def get_target_temperature(self) -> float | None:
    """Retrieve the VTherm's current target temperature.

    Reads the live state of the underlying climate entity; implementations
    must not cache a previously observed value.

    Returns:
        Current target temperature in Celsius, or ``None`` when the VTherm
        entity is unavailable or its target temperature cannot be read.
    """
```

Implemented in `infrastructure/adapters/climate_data_reader.py`, reusing the existing
VTherm-attribute-reading helpers (same `temperature` climate attribute already read
elsewhere in this adapter family). No new constructor dependency — the adapter already holds
the VTherm entity id.

## 2. `ISchedulerReader.get_next_timeslot` — new parameter

File: `domain/interfaces/scheduler_reader_interface.py`

```python
@abstractmethod
async def get_next_timeslot(
    self, exclude_entity_ids: frozenset[str] = frozenset()
) -> ScheduledTimeslot | None:
    """Retrieve the next scheduled heating timeslot.

    Scans all configured scheduler entities except those listed in
    ``exclude_entity_ids`` and returns the earliest upcoming timeslot with a
    valid time and temperature among the remaining ones.

    Args:
        exclude_entity_ids: Scheduler entity ids to skip for this call —
            typically schedulers already confirmed blocked earlier in the
            same recalculation cycle. Empty by default, which reproduces
            today's behavior exactly.

    Returns:
        The next schedule timeslot among non-excluded schedulers, or
        ``None`` if none qualify or no scheduler entities are configured.
    """
```

Default empty `frozenset` means every existing call site (both `simple_decision_strategy.py`
and `ml_decision_strategy.py` in the domain layer, and `calculate_anticipation_use_case.py`)
keeps compiling and behaving identically without being touched, satisfying User Stories 2/3.
`HASchedulerReader.get_next_timeslot()` implements the filter by skipping excluded entity ids
in its existing scan loop — no change to per-entity extraction logic.

## 3. `ISchedulerCommander.run_action` — return type changes from `None` to `bool`

File: `domain/interfaces/scheduler_commander_interface.py`

```python
@abstractmethod
async def run_action(self, target_time: datetime, scheduler_entity_id: str) -> bool:
    """Trigger a scheduler action for a specific timeslot.

    This will start heating in the mode configured in the scheduler for the
    timeslot at the given time. Never bypasses the scheduler's own
    conditions (no ``skip_conditions`` override).

    Args:
        target_time: The time of the scheduler timeslot to trigger
        scheduler_entity_id: Scheduler entity ID to control

    Returns:
        ``True`` if an actuation attempt was made on the underlying HACS
        Scheduler (whether or not its conditions ultimately let the action
        through — that is for the caller to verify separately). ``False``
        for a native HA schedule entity, which this adapter never actuates
        (compute-only, per [[ihp-computes-not-actuates]]).

    Raises:
        ValueError: If scheduler entity is not configured
    """
```

`HASchedulerCommander.run_action()` keeps its existing native-schedule early return (now
returning `False` instead of `None`) and returns `True` after the existing
`scheduler.run_action` service call. `cancel_action()` is unaffected (revert path is not in
scope for this feature).

## 4. `ControlPreheatingUseCase.start_preheating` — return type changes from `None` to `bool`

File: `application/use_cases/control_preheating_use_case.py` (not a domain ABC; application
use case, documented here because its contract with callers changes)

```python
async def start_preheating(
    self,
    target_time: datetime,
    target_temp: float,
    scheduler_entity_id: str,
) -> bool:
    """Start preheating by triggering scheduler action and verifying its effect.

    Args:
        target_time: Target schedule time
        target_temp: Target temperature
        scheduler_entity_id: Scheduler entity to trigger

    Returns:
        ``True`` when preheating may proceed normally: either the action's
        effect was confirmed (VTherm's resulting target temperature matches
        ``target_temp`` within ``TARGET_TEMP_MATCH_TOLERANCE_C``), the
        scheduler is a native schedule (nothing to verify), or the VTherm's
        state could not be read (unproven failure — treated as success per
        the resolved clarification). ``False`` only when the mismatch was
        positively confirmed — the caller should attempt the next candidate
        scheduler instead.
    """
```

**Critical state-mutation rule** (found during `/speckit.checklist` review of this plan):
`is_preheating_active`, `preheating_target_time`, and `active_scheduler_entity` MUST be set
only on a `True` return. On a confirmed `False`, none of that state may be mutated. This is
not optional polish — `ScheduleAnticipationActionUseCase.schedule_action()` gates its own
"trigger now" and "schedule timer" branches on
`not self._control_preheating.is_preheating_active()`. If a blocked attempt were allowed to
flip that flag anyway, the orchestrator's same-cycle retry on the fallback candidate would
find `is_preheating_active() == True` and skip calling `start_preheating()` for it entirely
— silently deadlocking the fallback this feature exists to deliver.

Requires a new **optional** constructor dependency: `climate_data_reader:
IClimateDataReader | None = None`, injected at the composition root
(`heating_application.py`) reusing the same instance already built for
`CalculateAnticipationUseCase`. Optional (not required) because 7 existing call sites
construct `ControlPreheatingUseCase` with only a commander (6 test fixtures/BDD steps plus
the pre-fix composition root) — making it required would force unrelated test breakage. When
`None`, verification is skipped and `start_preheating()` returns `True` unconditionally,
identical to the "VTherm state unreadable" case — both are "cannot prove failure," so both
resolve the same way per the clarified semantics.

## 5. `ScheduleAnticipationActionUseCase` — surfaces a blocked scheduler

File: `application/use_cases/schedule_anticipation_action_use_case.py`

`handle_anticipation_scheduling()`, `schedule_action()`, and `_trigger_action()` change their
return type from `None` to `str | None`: the blocked scheduler's entity id when
`ControlPreheatingUseCase.start_preheating()` returned `False`, otherwise `None`. No other
behavior changes — revert/timer logic is untouched.

**Amendment found during implementation**: the *synchronous* path (anticipated start already
past — `schedule_action()` triggers immediately, inside the orchestrator's awaited call) can
propagate this return value straight up to the orchestrator's retry loop (§7). The *timer-fired*
path cannot: `_timer_callback` (inside `_schedule_timer`) runs later, driven by
`ITimerScheduler`, entirely outside any orchestrator call that is still awaiting a result — a
return value from `_trigger_action` at that point has no caller left to receive it. To let that
path participate in the same retry loop, the constructor gains one more **optional** parameter:

```python
def __init__(
    self,
    scheduler_reader: ISchedulerReader,
    scheduler_commander: ISchedulerCommander,
    timer_scheduler: ITimerScheduler,
    control_preheating_use_case,
    anticipation_recalc_tolerance_minutes: int = DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    on_scheduler_blocked: Callable[[str], Awaitable[None]] | None = None,
) -> None: ...

def set_on_scheduler_blocked(self, callback: Callable[[str], Awaitable[None]] | None) -> None:
    """Set the callback invoked when a timer-fired trigger is confirmed blocked.

    Wired by the composition root *after* the orchestrator is constructed —
    this breaks the circular dependency between this use case (built first)
    and the orchestrator (which owns the retry loop this callback re-enters).
    """
```

`_timer_callback` becomes: call `_trigger_action()`; if it returns a blocked entity id and
`on_scheduler_blocked` is set, `await on_scheduler_blocked(blocked_entity_id)`. Optional and
defaulting to `None` keeps every existing construction site (4+ test fixtures/BDD steps)
compiling unchanged — without it, a timer-fired block is still logged and returned by
`_trigger_action()` (useful for direct unit testing of that method), it just has no one to
hand the retry to, identical to today's behavior.

## 6. `CalculateAnticipationUseCase.calculate_anticipation_datas` — new parameter

File: `application/use_cases/calculate_anticipation_use_case.py`

```python
async def calculate_anticipation_datas(
    self,
    target_time: datetime | None = None,
    target_temp: float | None = None,
    exclude_entity_ids: frozenset[str] = frozenset(),
) -> dict:
    """... (existing docstring, plus:)

    Args:
        exclude_entity_ids: Scheduler entity ids to exclude from candidate
            selection this call — forwarded to
            ``ISchedulerReader.get_next_timeslot()``. Empty by default.
    """
```

Forwards directly to `self._scheduler_reader.get_next_timeslot(exclude_entity_ids=...)`
(only used in the `target_time is None` branch, which already calls the reader).

## 7. `HeatingOrchestrator` — owns the retry loop, including the timer-fired re-entry

File: `application/orchestrator.py`

No interface/ABC — internal composition change. The retry loop is extracted into a shared
helper so both the normal entry point and the timer-fired callback (§5 amendment) use it:

```python
async def calculate_and_schedule_anticipation(self, ihp_enabled: bool = True) -> dict[str, Any]:
    return await self._run_anticipation_cycle(ihp_enabled, frozenset())

async def retry_anticipation_after_blocked_scheduler(self, blocked_entity_id: str) -> None:
    """Re-enter the cycle, excluding a scheduler a timer-fired trigger just confirmed
    blocked. Called by ScheduleAnticipationActionUseCase's on_scheduler_blocked callback —
    not part of the integration-facing API."""
    await self._run_anticipation_cycle(True, frozenset({blocked_entity_id}))

async def _run_anticipation_cycle(
    self, ihp_enabled: bool, seed_excluded: frozenset[str]
) -> dict[str, Any]:
    excluded = seed_excluded
    blocked: list[str] = list(seed_excluded)
    while True:
        anticipation_data = await self._calculate_anticipation.calculate_anticipation_datas(
            exclude_entity_ids=excluded
        )
        blocked_entity = await self._schedule_anticipation_action.handle_anticipation_scheduling(
            anticipation_data, ihp_enabled
        )
        if blocked_entity is None:
            break
        blocked.append(blocked_entity)
        excluded = excluded | {blocked_entity}
        if anticipation_data.get("scheduler_entity") is None:
            break  # no candidate was even attempted; nothing to retry

    anticipation_data["scheduler_blocked"] = bool(blocked) and (
        anticipation_data.get("anticipated_start_time") is None
    )
    anticipation_data["blocked_schedulers"] = blocked
    if anticipation_data["scheduler_blocked"]:
        _LOGGER.warning("All configured schedulers are blocked this cycle: %s", blocked)
    return anticipation_data
```

The loop terminates because `excluded` strictly grows each iteration and
`get_next_timeslot()` only ever considers configured, non-excluded entities — once all are
excluded it returns `None`, which `calculate_anticipation_datas()` turns into
`anticipated_start_time: None`, which `handle_anticipation_scheduling()` already treats as
"cancel everything" (existing Decision 1) without attempting a new trigger.

Composition root wiring (`heating_application.py`): construct `schedule_anticipation_action`
with `on_scheduler_blocked=None` (as today), construct `orchestrator`, then call
`schedule_anticipation_action.set_on_scheduler_blocked(orchestrator.retry_anticipation_after_blocked_scheduler)`
— this one extra line breaks the construction-order circular dependency. The callback itself
is wrapped in `heating_application.py` to acquire `_learning_lock` before re-entering the
cycle, so this timer-fired re-entry cannot interleave with the periodic recalculation in
`_async_update_locked()` (both mutate the same use-case instances' state). `event_bridge.py`'s
own VTherm-change-triggered recalculation call was already unprotected by any lock before
this feature and is left as-is — a pre-existing gap, out of this fix's scope.

## 8. `ScheduleAnticipationActionUseCase._cancel_preheating_for_other_slot` — stability fix found during implementation

File: `application/use_cases/schedule_anticipation_action_use_case.py`

**Not in the original design** — found and fixed via an empirical regression test while
implementing US1. Because a fresh recalculation always recomputes "next timeslot" starting
from the earliest configured scheduler (per the user's cycle-scoped-exclusion decision), a
second recalculation tick, while a successful fallback is still actively preheating,
recomputes the earliest (still-blocked) scheduler again - and the pre-existing
`_cancel_preheating_for_other_slot` reverted the active, correctly-preheating fallback purely
because this tick's freshly computed candidate's target time differed, immediately before the
fallback was about to be re-confirmed. This reintroduced the comfort/eco setpoint flapping
issue 0.6.x already fixed once (#182), every recalculation tick, for as long as the earlier
scheduler's own slot time hadn't yet elapsed.

Fix: `_cancel_preheating_for_other_slot` no longer reverts when the currently active
scheduler is still enabled (`ISchedulerReader.is_scheduler_enabled()`), regardless of whether
this tick's freshly computed candidate differs. It still reverts when the active scheduler is
genuinely no longer usable (disabled/removed), preserving the original "slot removed or
moved" behavior this method was built for.

**Known accepted limitation**: with this fix, while the fallback remains active, the
earliest-but-blocked scheduler's own retry probe is itself skipped too (`schedule_action`'s
pre-existing "already preheating, continuing" branch triggers, since nothing was reverted) -
so `anticipation_data` briefly reports the earliest candidate's own target/time as
`scheduler_entity`/`next_schedule_time` on that tick, rather than the fallback's, even though
the fallback is what is actually running. This is a sensor-display staleness only (no
actuation is affected - the thermostat is never touched); accepted rather than adding further
complexity to resolve within this fix.
