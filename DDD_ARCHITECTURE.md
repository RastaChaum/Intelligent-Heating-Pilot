# Domain-Driven Design Architecture

## Overview

The Intelligent Heating Pilot (IHP) integration follows a **Domain-Driven Design (DDD)** architecture with strict separation of concerns. This document explains the architectural structure and how different components interact.

## Why DDD?

Domain-Driven Design provides several key benefits for this project:

1. **Testability**: Pure domain logic can be tested without Home Assistant
2. **Maintainability**: Clear boundaries make the code easier to understand and modify
3. **Flexibility**: Infrastructure (Home Assistant) can be swapped without touching business logic
4. **Portability**: Domain logic can potentially work with other home automation systems
5. **Clarity**: Business rules are explicit and centralized

## Layer Architecture

```
custom_components/smart_starter_vtherm/
├── domain/                      # Pure business logic (NO Home Assistant)
│   ├── value_objects/          # Immutable data carriers
│   │   ├── environment_state.py
│   │   ├── schedule_event.py
│   │   ├── prediction_result.py
│   │   └── heating_decision.py
│   ├── entities/               # Objects with identity
│   │   └── pilot_controller.py (Aggregate Root)
│   ├── interfaces/             # Contracts (ABCs)
│   │   ├── scheduler_reader.py
│   │   ├── model_storage.py
│   │   └── climate_commander.py
│   └── services/               # Domain services
│       └── prediction_service.py
│
├── infrastructure/             # Home Assistant integration (FUTURE)
│   ├── adapters/              # HA API implementations
│   └── repositories/          # Data persistence
│
└── application/               # Orchestration (FUTURE)
    └── use_cases/            # Application-specific logic
```

## Domain Layer

### Value Objects

**Immutable data carriers** that represent concepts in the heating domain:

- **`EnvironmentState`**: Current conditions (temperature, humidity, etc.)
- **`ScheduleEvent`**: A scheduled heating target
- **`PredictionResult`**: Calculated start time and duration
- **`HeatingDecision`**: What action to take (start, stop, monitor)

**Key characteristics:**
- Frozen dataclasses (`@dataclass(frozen=True)`)
- Input validation in `__post_init__`
- No behavior, just data

**Example:**
```python
state = EnvironmentState(
    current_temp=18.0,
    outdoor_temp=5.0,
    humidity=60.0,
    timestamp=datetime.now(),
)
```

### Entities

**Objects with identity and lifecycle:**

- **`PilotController`** (Aggregate Root): Orchestrates heating decisions
  - Coordinates between scheduler, storage, and climate control
  - Makes decisions based on domain logic
  - Does NOT know about Home Assistant

**Key characteristics:**
- Has methods that modify state
- Coordinates domain services
- Uses interfaces for external interactions

### Interfaces (ABCs)

**Contracts that define how domain interacts with external systems:**

- **`ISchedulerReader`**: Read scheduled events
- **`IModelStorage`**: Persist/retrieve learned data
- **`IClimateCommander`**: Control heating system

**Key characteristics:**
- Abstract Base Classes (ABC)
- Define "what" not "how"
- Enable mocking in tests
- No implementation details

**Example:**
```python
class ISchedulerReader(ABC):
    @abstractmethod
    async def get_next_event(self) -> ScheduleEvent | None:
        """Retrieve the next scheduled heating event."""
        pass
```

### Domain Services

**Stateless operations on domain objects:**

- **`PredictionService`**: Calculates heating start times
  - Pure calculation logic
  - No side effects
  - Testable without mocks

**Example:**
```python
prediction = prediction_service.predict_heating_time(
    current_temp=18.0,
    target_temp=21.0,
    outdoor_temp=10.0,
    humidity=50.0,
    learned_slope=2.0,
)
```

## Infrastructure Layer (Future)

The infrastructure layer will contain Home Assistant-specific code:

### Adapters

**Implementations of domain interfaces:**

- `HASchedulerAdapter` implements `ISchedulerReader`
- `HAStorageAdapter` implements `IModelStorage`
- `HAClimateAdapter` implements `IClimateCommander`

**Key characteristics:**
- Imports from `homeassistant.*` are ALLOWED here
- Thin translation layer (no business logic)
- Implements domain interfaces
- Handles HA-specific concerns (entity states, service calls)

### Example (Future Implementation)

```python
class HASchedulerAdapter(ISchedulerReader):
    """Home Assistant scheduler adapter."""
    
    def __init__(self, hass: HomeAssistant, entity_id: str):
        self._hass = hass
        self._entity_id = entity_id
    
    async def get_next_event(self) -> ScheduleEvent | None:
        """Read next event from HA scheduler entity."""
        state = self._hass.states.get(self._entity_id)
        if not state:
            return None
        
        # Extract data from HA state
        attrs = state.attributes
        next_time = parse_datetime(attrs.get("next_trigger"))
        target_temp = self._extract_temp(attrs)
        
        # Return domain value object
        return ScheduleEvent(
            target_time=next_time,
            target_temp=target_temp,
            event_id=self._entity_id,
        )
```

## Testing Strategy

### Unit Tests (Current)

Test domain layer in isolation:

```python
# tests/unit/domain/test_pilot_controller.py
def test_pilot_decides_to_start_heating():
    # GIVEN: Mock interfaces
    mock_scheduler = Mock(spec=ISchedulerReader)
    mock_storage = Mock(spec=IModelStorage)
    mock_commander = Mock(spec=IClimateCommander)
    
    # Configure mocks
    mock_scheduler.get_next_event.return_value = ScheduleEvent(...)
    mock_storage.get_learned_heating_slope.return_value = 2.0
    
    # WHEN: Make decision
    controller = PilotController(
        scheduler_reader=mock_scheduler,
        model_storage=mock_storage,
        climate_commander=mock_commander,
    )
    
    environment = EnvironmentState(...)
    decision = await controller.decide_heating_action(environment)
    
    # THEN: Should start heating
    assert decision.action == HeatingAction.START_HEATING
```

**Benefits:**
- Fast (milliseconds)
- No Home Assistant required
- Tests business logic only
- Easy to debug

### Integration Tests (Future)

Test with real Home Assistant:

```python
# tests/integration/test_ha_integration.py
async def test_full_heating_cycle(hass):
    """Test complete heating cycle with real HA."""
    # Setup real HA entities
    # Create real adapters
    # Execute full flow
    # Verify HA state changes
```

## Migration Path

The existing code can be migrated gradually:

1. ✅ **Phase 1: Define abstractions** (DONE)
   - Create domain layer structure
   - Define value objects and interfaces
   - Add unit tests

2. **Phase 2: Extract domain logic** (FUTURE)
   - Move calculation logic to domain services
   - Extract decision-making to PilotController
   - Keep existing code working alongside

3. **Phase 3: Implement adapters** (FUTURE)
   - Create HA adapters implementing interfaces
   - Wire up domain and infrastructure
   - Gradually replace old code

4. **Phase 4: Complete migration** (FUTURE)
   - Remove old coupled code
   - Full test coverage
   - Documentation updates

## Benefits Achieved

### Before (Coupled Code)
```python
def calculate_anticipation(self):
    vtherm_state = self.hass.states.get(self.vtherm_entity)
    temp = vtherm_state.attributes.get("temperature")
    scheduler_state = self.hass.states.get(self.scheduler)
    # Business logic mixed with HA API calls
    if temp < target:
        self.hass.services.call("climate", "turn_on")
```

**Problems:**
- Cannot test without Home Assistant
- Business logic hidden in infrastructure code
- Hard to understand what the code does
- Difficult to change

### After (DDD Architecture)
```python
# Domain layer - testable, clear
async def decide_heating_action(self, env: EnvironmentState) -> HeatingDecision:
    next_event = await self._scheduler.get_next_event()
    prediction = self._prediction_service.predict_heating_time(...)
    
    if prediction.anticipated_start_time <= env.timestamp:
        return HeatingDecision(
            action=HeatingAction.START_HEATING,
            target_temp=next_event.target_temp,
            reason="Time to start heating"
        )
    # Clear business logic

# Infrastructure layer - thin adapter
class HAClimateAdapter(IClimateCommander):
    async def start_heating(self, target_temp: float) -> None:
        await self._hass.services.async_call(
            "climate", "set_temperature",
            {"entity_id": self._entity_id, "temperature": target_temp}
        )
```

**Benefits:**
- Domain logic testable without HA
- Clear separation of concerns
- Business rules explicit
- Easy to modify and extend

## Design Principles

### 1. Dependency Inversion

Domain defines interfaces, infrastructure implements them:
```
Domain (interfaces) ← Infrastructure (implementations)
```

### 2. Pure Functions

Domain services use pure functions when possible:
```python
# Input → Output, no side effects
def calculate_duration(temp_delta: float, slope: float) -> float:
    return (temp_delta / slope) * 60.0
```

### 3. Immutability

Value objects are immutable:
```python
@dataclass(frozen=True)
class EnvironmentState:
    current_temp: float
    # Cannot be modified after creation
```

### 4. Single Responsibility

Each class has one reason to change:
- `PilotController`: Heating decision logic
- `PredictionService`: Calculation algorithms
- `HASchedulerAdapter`: HA scheduler interaction

### 5. Interface Segregation

Small, focused interfaces:
- `ISchedulerReader`: Only reads schedules
- `IClimateCommander`: Only controls climate
- `IModelStorage`: Only persists data

## Summary

The DDD architecture provides a solid foundation for the Intelligent Heating Pilot:

- ✅ **Domain layer is pure business logic** - No HA dependencies
- ✅ **Interfaces define contracts** - Clear boundaries
- ✅ **Value objects are immutable** - Safe data handling
- ✅ **Unit tests verify domain logic** - Fast, reliable tests
- 🔄 **Infrastructure layer planned** - HA integration coming
- 🔄 **Gradual migration path** - Won't break existing functionality

This architecture makes the code more maintainable, testable, and flexible for future enhancements.
