# End-to-end tests

These tests start a throw-away **Home Assistant container** (the official image, pinned in
`stack.py`) with IHP, Versatile Thermostat, HACS Scheduler and Climate Scheduler, and drive it
through its REST and WebSocket APIs. They run on the real clock, so they take about fifteen
minutes and are skipped unless asked for.

```bash
IHP_E2E=1 poetry run pytest tests/e2e -v
IHP_E2E=1 IHP_E2E_HA_IMAGE=ghcr.io/home-assistant/home-assistant:beta poetry run pytest tests/e2e -v
```

They need Docker and network access (the image, then the third-party releases pinned in
`tests/integration/real_components/components.json`).

## What one run checks

One container holds three rooms. Each has a real Versatile Thermostat, an IHP and one scheduler:
a native `schedule`, HACS Scheduler, Climate Scheduler. Their slot starts about ten minutes after
the scenario is set up.

- every config entry loads;
- IHP publishes its entities for each room;
- IHP puts the thermostat in the slot's preset **before** the slot starts, on every scheduler;
- the Home Assistant log holds no unexpected error from IHP or its companions;
- everything loads again after a restart.

## How it works

- `stack.py`: writes `configuration.yaml` and the seeded config entries, starts the container,
  creates the owner through the onboarding API, and offers `state`, `call`, `websocket`,
  `restart` and `logs`.
- Rooms are simulated with helpers (`input_number` for the sensor, `input_boolean` for the
  heater); the thermostats, schedulers and IHP are the real integrations.
- The native schedule and the schedulers are created at run time, so their slot is relative to
  the real clock.

## Pitfalls

- Climate Scheduler creates the switch of a group only when it loads: the scenario calls its
  `reload_integration` service after creating the group.
- A schedule block cannot cross midnight, so the block is cut at 23:59:59 when the test runs late
  in the evening.
- The container log is saved to `IHP_E2E_LOG_DIR` (or the test's temporary directory) even when
  a test fails.
