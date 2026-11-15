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
- `home.py` builds a small home (thermostat, sensors, IHP) and moves the clock with `advance`.
- Each scenario sets up a scheduler, lets IHP anticipate its next slot, advances the clock to the
  anticipated start and checks the state of the real thermostat.

```bash
poetry run pytest tests/integration/real_components -v
```

## Updating a component

Change the `tag` in `components.json`, then fill `sha256` with the checksum of the new archive:

```bash
curl -sL https://github.com/<repository>/archive/refs/tags/<tag>.tar.gz | sha256sum
```

## Pitfalls

- Use the `clock` fixture and `advance`, not `freezer` with `async_block_till_done`: a component
  that sleeps or waits with a timeout never wakes up on a frozen clock unless the clock moves
  forward and the due timers are fired.
- Request `real_components` (it pulls `recorder_mock` before `hass`).
