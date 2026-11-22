# Architecture Overview

Intelligent Heating Pilot follows a Domain-Driven Design structure that keeps heating logic isolated from Home Assistant details.

## Layer Model

```text
custom_components/intelligent_heating_pilot/
├── domain/          Pure business logic
├── application/     Use cases and orchestration
└── infrastructure/  Home Assistant adapters and persistence
```

## Layer Responsibilities

### Domain

- Contains heating rules, calculations, and value objects.
- Must not import `homeassistant.*`.
- Communicates outward only through interfaces.

### Application

- Coordinates domain services and infrastructure adapters.
- Encodes use cases such as cycle lifecycle management and anticipation scheduling.
- Keeps orchestration separate from the underlying Home Assistant API surface.

### Infrastructure

- Adapts Home Assistant entities, services, and storage to domain interfaces.
- Must stay thin and avoid business decisions.

### Settings and the Central Configuration

- The domain `SettingsCatalog` declares every configurable setting (theme, shareable or device-only, default); `SettingsResolver` applies the rule *device value, else central value, else built-in default*. A key present in a device's data or options is an override; `None` is a valid override of an optional sensor.
- The central configuration is a config entry of the same domain (`entry_type: central`, fixed unique id). It creates no coordinator and no entity; it is created automatically with the first device and read through `ICentralConfigReader`.
- The options flows (`config_flow_themes.py`, `config_flow_overrides.py`) store each theme at once without reloading; "Apply" reloads the device, or, for the central entry, the devices that inherit a changed value.

## Main Runtime Flow

1. Infrastructure reads VTherm, scheduler, and environment state.
2. Application services orchestrate extraction, learning, and anticipation updates.
3. Domain services calculate heating slope, dead time, and start times.
4. Infrastructure publishes sensor state and triggers scheduler or climate actions.

## Actuation Principle

**The scheduler decides what happens, when, and whether it happens. IHP decides how early.**

At the anticipated start, IHP applies the next slot's own action (a preset or a temperature) to the climate entity. At the slot time the scheduler applies the same action, which changes nothing. IHP never preheats a slot its scheduler would not run.

Use cases ask one question of one port, `IPreheatActuator`: "start the preheat of this slot". Which integration answers is decided outside the domain:

| Scheduler | Owner found from | Actuation |
|-----------|------------------|-----------|
| HACS Scheduler | entity registry platform `scheduler` | delegated: IHP calls its `run_action` (it can evaluate conditions) |
| Climate Scheduler | platform `climate_scheduler` | direct: IHP applies the node's action to the climate |
| Native `schedule.*` | entity domain | direct, only when the user opts in |
| Anything else | | computed only: nothing is sent, nothing fails |

Direct control records the climate's state once per slot, before the first command, and puts it back only if nobody else changed it meanwhile. The rules live in a pure domain service (`PreheatSessionPolicy`); `DirectPreheatActuator` composes ports and that policy, and every Home Assistant call stays in a thin adapter. Each command carries a context that has a parent, so that schedulers watching for manual changes do not take it for one.

## Deadline Sources

The next deadline IHP anticipates comes from one question on one port, `ISchedulerReader.get_next_timeslot`. `CombinedTimeslotReader` (application layer) answers it from two kinds of candidates: the schedulers' slots, and the **wake-up sources** an IHP lists in its options (entities holding a point in time). The earliest valid one wins; the scheduler's slot wins a tie. No consumer of the port knows that sources exist.

| Piece | Layer | Role |
|-------|-------|------|
| `WakeUpDeadlinePolicy` | domain service | Is a source's value a deadline: not unknown, not past, within the horizon |
| `WakeUpTargetPolicy` | domain service | The fixed target, or the schedule's (never lower than the slot in effect), with fallbacks |
| `IWakeUpSourceReader`, `IScheduleSlotLookup`, `IPresetTemperatureResolver` | domain ports | Read a source, read the schedule slots around a moment, tell a preset's temperature |
| `SchedulerKind.TIMESTAMP` | domain | A source's slots are routed to the direct actuator |
| `HAWakeUpSourceReader`, `HAScheduleSlotLookup` | infrastructure | Translate states and schedule attributes; no rule |

A source slot's identity is its entity and the local date of its deadline, not the time, so a snooze keeps the record and any claim made by someone else. A deadline that moves, or a closer one, is handed over (`IPreheatActuator.hand_over`) with no restore in between. An optional hold keeps the record after the deadline (`begin_hold`, `end_hold`) until a timer ends it, unless a scheduler slot comes first.

## Key Concepts

- Global LHS: fallback heating slope computed across all valid cycles.
- Contextual LHS: hour-specific heating slope used when enough local history exists.
- Dead Time: startup lag excluded from the effective heating duration.
- Cycle Cache: persisted heating-cycle history used to avoid repeated recorder scans.

## Related Documentation

- [CACHE_SYSTEM.md](CACHE_SYSTEM.md)
- [../users/HOW_IT_WORKS.md](../users/HOW_IT_WORKS.md)
- [../contributors/CONTRIBUTING.md](../contributors/CONTRIBUTING.md)
- [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md)
