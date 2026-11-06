# Research: Anticipation Falls Back When a Scheduler's Conditions Block It

**Feature**: [spec.md](./spec.md) | **Date**: 2026-10-26

No `[NEEDS CLARIFICATION]` markers remained in the Technical Context after planning — the
two product-level ambiguities were resolved with the user during `/speckit.clarify` (see
spec's `## Clarifications`). This document records the technical investigation that shaped
the design, and the implementation-level decisions made from it.

## 1. Can scheduler-component's future condition state be read in advance? (Option A)

**Question**: Issue #64 proposed, as its preferred option, filtering candidate schedulers by
whether their conditions will hold at the anticipated time — *if* that data is exposed.

**Investigation**: Fetched `nielsfaber/scheduler-component`'s actual source
(`custom_components/scheduler/switch.py`, `actions.py`) via the GitHub API.

- `switch.py`'s `state_attributes` property exposes exactly: `weekdays`, `timeslots` (start/
  stop time-range strings), `entities`, `actions` (one summarized service call per timeslot),
  `current_slot`, `next_slot`, `next_trigger`, `tags`. **No `conditions` or `condition_type`
  attribute is exposed.**
- `actions.py` shows conditions (`CONF_CONDITIONS`, entity/match_type/value) live only in the
  integration's internal `ScheduleEntry` config dict (`self.schedule`), never written to HA
  state. They are evaluated by `validate_condition()` only when `async_process_queue()` runs
  — i.e. at actual trigger time, against *current* entity states; there is no API that
  forecasts a future evaluation.

**Decision**: Option A is not implementable through the integration's public, documented
surface. Reaching into its internal config store would mean depending on an unversioned,
undocumented schema — exactly what `HASchedulerReader`'s own docstring ("this adapter
contains NO business logic — it only translates HA states") and the project's
infrastructure rules forbid. **Rejected.**

**Alternatives considered**: Re-implementing scheduler-component's `is`/`not`/`below`/`above`
condition evaluation inside IHP using whatever entity ids could be scraped from undocumented
attributes — rejected for the same coupling reason, plus it would duplicate business logic
that belongs to another integration entirely.

## 2. Can a triggered action's effect be verified without polling/sleeping?

**Question**: Option B (the issue's own fallback suggestion) requires detecting whether
`run_action` actually changed the climate entity. A naive approach polls for a few seconds.

**Investigation**: In `switch.py`, `async_service_run_action()` is `await`-ed by
`HASchedulerCommander.run_action()` with `blocking=True`. Internally, it calls
`self._action_handler.async_queue_actions(schedule)`, which calls
`queue.async_start(skip_initial_execution=False)`, which — when not deferred — calls
`await self.async_process_queue()` **synchronously**, in the same call stack. That method
validates conditions and, if they hold, dispatches the nested `climate.set_temperature` /
`climate.set_preset_mode` call via `async_call_from_config` (also awaited).

**Decision**: Because the whole chain is awaited synchronously down to the nested service
call, **the climate entity's state already reflects the outcome by the time
`HASchedulerCommander.run_action()` returns**. No polling, no sleep, no timer window needed —
a single state read right after the awaited call is sufficient and deterministic (and
therefore trivially unit-testable without `freezegun`/fake clocks).

**Alternatives considered**: Poll VTherm for N seconds after triggering — rejected: adds
latency, flakiness in tests, and is unnecessary given the synchronous chain above.

## 3. What signals "the action had no effect"?

**Decision**: Compare the VTherm's resulting target temperature (`temperature` climate
attribute) to the `target_temp` IHP itself passed into `start_preheating()` — the exact value
the triggered scheduler action was expected to apply, already resolved by
`HASchedulerReader` the same way whether the action is `climate.set_temperature` or
`climate.set_preset_mode` (see `ScheduledTimeslot.target_temp`). A direct comparison is
apples-to-apples; no unit conversion sits between them.

A small tolerance constant (`TARGET_TEMP_MATCH_TOLERANCE_C = 0.05`) absorbs floating-point
noise only — not a user-facing tuning knob (no config option), consistent with the "no magic
numbers — named constants" project rule. 0.05°C is far below VTherm's typical 0.1-0.5°C step,
so it cannot mask a real mismatch while still absorbing representation noise.

**Resolved per `/speckit.clarify`**: if the VTherm's resulting state cannot be read at all
(`unavailable`/`unknown`), this is *not* treated as a confirmed mismatch — IHP does not fall
back (see spec Clarifications for rationale).

## 4. Where does "attempted vs. not attempted" belong?

**Question**: Native `schedule.*` entities are never actuated (existing design,
[[ihp-computes-not-actuates]]); verification must not run for them, but that knowledge
currently lives only inside `HASchedulerCommander` (`NATIVE_SCHEDULE_PREFIX`).

**Decision**: `ISchedulerCommander.run_action()` returns `bool` — `True` when an actuation
attempt was made (HACS `switch.*`), `False` for a native schedule no-op. This is a plain
infrastructure-translation fact (what happened, not a business rule), so it belongs on the
commander. `ControlPreheatingUseCase.start_preheating()` only performs the temperature
comparison when `attempted` is `True`; for `False` it returns `True` ("proceed normally"),
preserving today's native-schedule behavior exactly (User Story 3).

**Alternatives considered**: Duplicating the `schedule.` prefix check in the application
layer — rejected (duplicates a fact the infrastructure layer already owns, breaks DRY).

## 5. Where does the retry/fallback decision belong?

**Investigation**: `ScheduleAnticipationActionUseCase` decides *when* to schedule or trigger,
but has no reference to `CalculateAnticipationUseCase` — and a fallback candidate has its
own target time/temperature that must be *recalculated* (LHS-based), not reused from the
blocked candidate. `HeatingOrchestrator.calculate_and_schedule_anticipation()` already calls
both use cases in sequence and is the only component holding both.

**Decision**: `ScheduleAnticipationActionUseCase` surfaces a confirmed-blocked scheduler
entity id back to its caller (return value) instead of swallowing it.
`HeatingOrchestrator.calculate_and_schedule_anticipation()` owns a small retry loop: on a
blocked signal, add the entity to a locally-scoped `exclude_entity_ids` set and re-run
`calculate_anticipation_datas(exclude_entity_ids=...)` → `handle_anticipation_scheduling()`,
bounded by the number of configured scheduler entities (so it always terminates). This keeps
`ScheduleAnticipationActionUseCase` focused on its existing responsibility (revert/timer
logic) and keeps the cross-use-case sequencing where it already lives.

**Alternatives considered**: Giving `ScheduleAnticipationActionUseCase` a direct reference to
`CalculateAnticipationUseCase` — rejected, it would blur its single responsibility and
duplicate sequencing the orchestrator already owns.

## 6. Observability of a fully-exhausted cycle

**Resolved per `/speckit.clarify`-adjacent decision with the user**: both a WARNING log (with
`friendly_name`) and a dashboard-visible signal are required. The existing `anticipation_data`
dict already flows into every anticipation-related sensor's `extra_state_attributes` (see
`sensor.py`); adding `"scheduler_blocked": bool` (and `"blocked_schedulers": list[str]` for
diagnostics) to that same dict reuses the existing plumbing — no new sensor entity needed.
