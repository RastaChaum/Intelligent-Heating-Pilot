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
