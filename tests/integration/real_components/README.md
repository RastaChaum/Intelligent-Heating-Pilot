# Real-component integration tests

These tests run IHP inside the Home Assistant test harness next to the **real** integrations it
works with, instead of mocks: Versatile Thermostat, HACS Scheduler, Climate Scheduler and Home
Assistant's native `schedule` helper. Only the physical devices (room and outdoor sensors, the
heater switch) are simulated.

They catch what the mocked suites cannot: a change in a scheduler's attributes or services, or in
Versatile Thermostat's behaviour, that would otherwise only show up on a live Home Assistant.

## How it works

- `components.json` pins each third-party release by tag **and** sha256.
- `fetch.py` downloads them into `.cache/real_components/custom_components/` (git-ignored) when
  the tests are collected, because DNS is disabled once a test runs. Without network access the
  tests are skipped, not failed.
- `home.py`: a `Home` is a cold room on a Monday at 05:00 heated by a real Versatile Thermostat.
  It starts IHP, moves the clock (`advance`) and reads the thermostat (`preset`, `target`,
  `commands_to_thermostat`).
- `schedulers.py`: one driver per scheduler (`NativeSchedule`, `HacsScheduler`,
  `ClimateScheduler`) turns a list of `Block` into the scheduler's own configuration, so a
  scenario is written once and parametrised on all three.

| File | Covers |
| --- | --- |
| `test_preheat_applies_the_action.py` | The same preheat on the three schedulers: preset, temperature, nothing early, hand-over at the slot, IHP switched off |
| `test_scheduler_specifics.py` | Native options (fallback preset, data keys, opt-in), HACS Scheduler conditions, Climate Scheduler disabled switch and temperature node |
| `test_preheat_restore.py` | Safe restore: removed or moved block, manual change, set by hand, imminent slot, restart, slot reached |
| `test_wake_up_sources.py` | Wake-up sources: earliest deadline, hold and restore, target from the schedule, snooze, removal, unknown alarm, restart during the hold |
| `test_generic_climate.py` | Home Assistant's own `generic_thermostat`, no Versatile Thermostat set up (#252): temperature and mapped preset slots on the three schedulers, unmapped preset warning, native default, the preset mapping step of the options flow |

`GenericThermostatHome` (fixture `generic_home`) is the same room heated by `generic_thermostat`. It
lists its presets but does not publish their temperatures, and it has no `boost` preset.

```bash
poetry run pytest tests/integration/real_components -v
```

Not covered here: a Climate Scheduler group of several rooms with a different value per room (its
service cannot express one), and HACS Scheduler cancellations, which the BDD features cover.

## Updating a component

Change the `tag` in `components.json`, then fill `sha256` with the checksum of the new archive:

```bash
curl -sL https://github.com/<repository>/archive/refs/tags/<tag>.tar.gz | sha256sum
```

## Pitfalls

- Use the `clock` fixture and `advance`, not `freezer` with `async_block_till_done`: a component
  that sleeps or waits with a timeout never wakes up on a frozen clock unless the clock moves
  forward and the due timers are fired.
- Request `real_components` (it pulls `recorder_mock` before `hass`), or the `home` fixture.
- The room sensor of `Home` reports a value that differs by 0.1°C every ten minutes, like a live
  one. Without it nothing wakes IHP up after it has applied an action, so a hold would never end.
- Versatile Thermostat publishes a preset's temperature in its attributes only once the preset
  has been selected; `Home` goes through each preset before the room rests.
- HACS Scheduler only runs a slot when "now" is strictly after its start: the clock starts half
  a second past the hour and only moves by whole seconds.
