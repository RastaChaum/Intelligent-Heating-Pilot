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
