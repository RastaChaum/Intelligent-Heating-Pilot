# Research: Adaptive wake-up from timestamp sources

Each entry: decision, rationale, alternatives. Facts below were read in the code at `d794cd5`; behavior not run is marked "to test".

## R1. Pull model: sources are configured entities

- **Decision**: a source is an entity listed in the IHP configuration; IHP reads it.
- **Rationale**: no automation needed for the shift-worker and #63 cases; state changes already trigger recalculation.
- **Alternatives**: a service pushing a one-off deadline (needs YAML, no persistence story). Kept for a later version; it would feed the same combined reader.

## R2. A combining reader behind the existing port

- **Decision**: `CombinedTimeslotReader` in the application layer implements `ISchedulerReader`, composing the scheduler reader, the source reader, the target policy and the climate reader. Consumers (calculation, strategies, use cases) are untouched.
- **Rationale**: `get_next_timeslot` already means "earliest candidate"; the decision strategies and the calculation use only that port. `RoutingPreheatActuator` shows the same pattern (application class implementing a domain port).
- **Alternatives**: grow `HASchedulerReader` (mixes two concerns and puts target rules in an adapter, against the adapter rule); rename the port to "timeslot reader" as the stale branch `feature/datetime-entity-support` did (pure churn in #292's area, deferred).

## R3. Slots around a moment, per scheduler kind

- **Finding**: all current readers answer "next slot from now". Native reads the weekly blocks through `schedule.get_schedule` (all blocks available). HACS and Climate Scheduler expose `next_trigger`, `next_slot` and `actions`; the other nodes' times are not read today.
- **Decision**: new port `IScheduleSlotLookup.get_slots_around(moment)`. Native: both slots computed from the blocks. HACS and Climate Scheduler: `following` only, and only when `next_trigger` is after the moment. `in_effect` is never inferred for them.
- **Rationale**: inferring the previous node cyclically is wrong for per-weekday schedules, and a wrong in-effect slot could lower a heated room. The Q4 rule (single slot used only if higher than the current target) was chosen for exactly this case.
- **Alternatives**: parse more attributes of each scheduler (unverified formats, per-integration breakage risk); to be revisited only if users report the fixed-target fallback too often.

## R4. Freeze the comparison against the pre-preheat setpoint

- **Finding**: Q4 compares a single slot's temperature with the thermostat's current target. After IHP raises the target, a recalculation would find "not higher" and switch to the fixed target mid-preheat.
- **Decision**: while a `PreheatRecord` exists for the same deadline, compare against `record.previous.temperature`; otherwise against the live snapshot.
- **Alternatives**: cache the resolved target per deadline in memory (lost on restart; the record is persisted already).

## R5. Ownership and routing

- **Finding**: the resolver answers from the entity registry; a phone alarm sensor belongs to `mobile_app` and would be `UNKNOWN` (computed only, one warning).
- **Decision**: add `SchedulerKind.TIMESTAMP`; the resolver is given the configured source ids and answers `TIMESTAMP` first; the routing table maps it to the direct actuator, with no opt-in (adding a source is the opt-in).
- **Alternatives**: a separate actuator class (the direct one already applies any `SlotAction`).

## R6. Reading a source value

- **Decision**: accept `sensor` with device class timestamp, `datetime`, and `input_datetime` with both date and time; state parsed to an aware datetime (naive values taken in the Home Assistant time zone). Date-only and time-only values are rejected and logged once.
- **Rationale**: these are the entities that hold a full point in time; a time-only helper has no day and would be a guess.
- **To test**: the parsing of each state format and DST edges.

## R7. Triggering recalculation

- **Finding**: the event bridge listens to scheduler ids and treats any change of the entity's own state as meaningful (`old_state.state != new_state.state`), so a source value change already qualifies.
- **Decision**: add source ids to the monitored list and route them through the same handler; no new filter.

## R8. Handover, removal, and the #292 cancel rule

- **Finding**: #292 cancels a preheat whose slot moved or vanished, except when the active scheduler's own next slot is still the preheated one (#64). `DirectPreheatActuator` already keeps the true original state when a record of an earlier slot is replaced by a new one.
- **Decision**: for Q3, when either slot is a source slot, start the new slot over the record instead of cancelling first; for Q2, a removed source goes through the existing cancel path. Scheduler-only behavior is unchanged.
- **To test**: snooze (moves later), closer new alarm, removal before and after start, the entity switching to the next day's alarm at the deadline.

## R9. Hold after the deadline

- **Finding**: on `SLOT_REACHED` the policy discards the record (guard window and "after the slot" give `DISCARD`), and `recover()` releases any record whose slot time has passed.
- **Decision**: `ScheduledTimeslot` gains an optional hold duration and `PreheatRecord` an optional `hold_until` (both default to absent, so stored records and existing slots read as before). For a source slot with a hold, `SLOT_REACHED` keeps the record and arms a timer. `recover()` keeps a record while `now < hold_until` and re-arms the timer. The hold ends early, without restore, when the next slot of a scheduler of that IHP comes first (Q1).
- **Alternatives**: restoring from an automation (the user asked for it to be in IHP); a fixed default hold (rejected: silent behavior change).

## R10. Configuration UI

- **Decision**: sources are stored as a list in the entry options. The options flow gets a menu step (add, edit, remove, done) and a form per source: entity, target mode (fixed or from the schedule), preset or temperature, horizon (hours, default 24), hold (minutes, optional). Validation per FR-007: a source with neither a fixed target nor "from the schedule" with a configured scheduler is refused; "from the schedule" without scheduler requires a fixed target.
- **Alternatives**: one source per IHP with plain fields (simpler, but FR-001 allows several and the options model would need migrating later); a YAML option (not Home Assistant style).

## R11. Learning and observability

- **Finding**: cycles come from temperature history and the contextual slope from the deadline's hour; the slot-history reader (#254) reads IHP's own Next Schedule Time sensor. Nothing in that path names a scheduler.
- **Decision**: no change expected; cover with a test that a source deadline is filed like a schedule one. The sensor's existing `scheduler_entity` attribute shows which source drives the deadline; no new sensor.
