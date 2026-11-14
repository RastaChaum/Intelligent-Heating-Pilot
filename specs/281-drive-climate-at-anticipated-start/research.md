# Research: Drive the climate at the anticipated start

Each entry gives the decision, the rationale (with the source read) and the alternatives rejected.
Upstream sources were read in local clones: scheduler-component v3.3.9, climate-scheduler
`d5dddf5`, ha-chauffage 0.9.0-beta.4, versatile_thermostat `e0b0a2f`, Home Assistant 2026.10.4.

## D1. Identify the scheduler from the entity registry

- **Decision**: a `switch.*` entity is owned by the integration named in its registry entry
  (`scheduler` for HACS Scheduler, `climate_scheduler` for Climate Scheduler). A `schedule.*`
  entity is native by its domain. Anything else, including a missing registry entry, is `UNKNOWN`.
- **Rationale**: Climate Scheduler deliberately mimics the HACS Scheduler attributes, so
  attributes cannot tell them apart. Both integrations register their switches with a unique id
  (scheduler-component `switch.py:441`, climate-scheduler `switch.py:102`).
- **Rejected**: guessing from attributes (what fails today); a user-selected scheduler type
  (more configuration for information Home Assistant already holds).

## D2. One port, two actuators, mode chosen in the composition root

- **Decision**: `IPreheatActuator` replaces `ISchedulerCommander`. `HacsRunActionActuator`
  delegates to `scheduler.run_action`; `DirectPreheatActuator` drives the climate. A
  `RoutingPreheatActuator` maps `SchedulerKind` to an actuator, built in the composition root.
- **Rationale**: #249 states that the choice of mode stays in infrastructure and the domain only
  sees "apply this slot". Replacing the old port, not adding beside it, avoids two paths for
  the same job.
- **Rejected**: a mode enum visible to the domain; keeping `ISchedulerCommander` next to a new
  port.

## D3. Restore and guard rules live in a pure domain policy

- **Decision**: `PreheatSessionPolicy` decides apply or skip and restore, leave or discard from
  value objects only.
- **Rationale**: they are business rules (never overwrite a user, never restore over the
  scheduler's own write) and must be testable without Home Assistant.
- **Rejected**: rules inside an adapter or inside `DirectPreheatActuator`.

## D4. Detect a change by another party by comparing requested state

- **Decision**: after acting, IHP compares the climate's current snapshot with the action it
  applied. For Versatile Thermostat the snapshot uses the `requested_state` attribute (hvac mode,
  target temperature, preset); for other climates, the standard attributes.
- **Rationale**: `preset_mode` and `temperature` also change because of safety, power shedding,
  window, presence and central mode (`state_manager.py`); `requested_state` is what a user or a
  scheduler asked for, and VTherm exposes it as a state attribute (`base_thermostat.py:834`).
- **Rejected**: comparing the visible preset or temperature (false positives); tracking the
  context of every state change (needs a listener and still cannot tell a scheduler's
  re-application from a user). Consequence: a change by another party is final for the slot.

## D5. Record once per slot, before the first write, and persist it

- **Decision**: `PreheatRecord` is saved before the first command for a slot, never replaced
  while the slot is the same, and kept across restart and reload (`IPreheatRecordStore`,
  Home Assistant `Store` per config entry).
- **Rationale**: a retry or a restart must not record IHP's own state as the previous one.
  The #156 bug class (a stale flag surviving a reload) shows persistence needs an owner.
- **Rejected**: an in-memory flag (lost at restart).

## D6. A preheat lasts only while its slot is its scheduler's next slot

- **Decision**: `_cancel_preheating_for_other_slot` compares the preheated slot with the **active
  scheduler's own** next slot (`get_next_timeslot_of`), not with the global earliest slot, and
  not with "the scheduler is enabled".
- **Rationale**: the current rule never reverts a moved or removed slot, which #249 requires.
  Comparing with the active scheduler's own next slot keeps the #64 flap fix (an earlier
  scheduler's candidate does not cancel a preheat in progress).
- **Rejected**: the global earliest slot (reintroduces the flap).

## D7. Native schedule: read `schedule.get_schedule`

- **Decision**: call the `schedule.get_schedule` service with a response; take the next block
  start after now, and read its `data` for the keys `native_schedule_preset_key` and
  `native_schedule_temperature_key`. Preset wins; temperature feeds the calculation. With no
  key, use the fallback preset.
- **Rationale**: `data` is exposed as attributes only while a block is running
  (`homeassistant/components/schedule/__init__.py:396`); `get_schedule` returns every block with
  its `data` (`:330`, `:430`). Reading block starts also anticipates adjacent ON blocks, which the
  current state-based reading skips.
- **Rejected**: a fixed `comfort` assumption for driving (IHP would invent the action); reading
  only the running block's attributes.

## D8. Climate Scheduler: node index from the node count per entity

- **Decision**: its `actions` list holds one entry per node and per entity, while `next_slot`
  indexes nodes (`switch.py:262`, `:297`). IHP reads the action at
  `next_slot * entity_count + position of its climate`. A node with no temperature and no
  preset (a "no change" node) yields no `SlotAction` and is skipped for driving.
- **Rationale**: wrong action or wrong room otherwise, for any group.
- **Accepted limitation**: after midnight the upstream picks the first node of today's schedule,
  which is wrong in 5/2 mode (`switch.py:243`). Documented, not worked around.

## D9. Apply with a context that has a parent

- **Decision**: `HAClimateCommander` sends every command with a `Context` whose `parent_id` is a
  fresh IHP context id.
- **Rationale**: ha-chauffage ignores a thermostat change when `context.parent_id is not None`
  and otherwise records an override (`runtime.py:1143`).

## D10. Command without effect: retry, no fallback

- **Decision**: clarification 3. `NOT_APPLIED` becomes the `RETRY` outcome; it logs once per
  slot and never falls back to another scheduler. The effect check reuses `wait_for_state_change`
  (#256), now comparing the snapshot, not only the temperature.
- **Rejected**: fallback to the next scheduler (only meaningful when a scheduler can block).

## D11. Explicitly not done

- HACS direct drive and the evaluation service: wait for scheduler-component#551, whose
  evaluation is only a forecast of conditions at call time.
- VTherm `set_timed_preset`: at its end it overwrites the requested preset with the original one
  (`feature_timed_preset_manager.py:330`), which would erase the scheduler's slot preset.
- ha-chauffage source: its next-change entity is not published in 0.9.0-beta.4.
- Slots that change the HVAC mode.
