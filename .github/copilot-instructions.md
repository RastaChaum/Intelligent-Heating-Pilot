# GitHub Copilot Instructions - Intelligent Heating Pilot (IHP)

## 🎯 Project Overview

The Intelligent Heating Pilot (IHP) is a Home Assistant integration that intelligently preheats homes using predictive algorithms and machine learning. This document defines the architectural principles and development practices that **must** be followed by all AI-assisted code generation.

## 🛡️ Architectural Mandate: Domain-Driven Design (DDD)

All development must follow **Domain-Driven Design** principles with strict separation of concerns.

### Layer Structure

```
custom_components/intelligent_heating_pilot/
├── domain/              # Pure business logic (NO Home Assistant dependencies)
│   ├── value_objects/   # Immutable data carriers
│   ├── entities/        # Domain entities and aggregates
│   ├── interfaces/      # Abstract base classes (contracts)
│   └── services/        # Domain services
├── infrastructure/      # Home Assistant integration layer
│   ├── adapters/        # HA API implementations
│   └── repositories/    # Data persistence implementations
└── application/         # Orchestration and use cases
```

### Domain Layer Rules (⚠️ CRITICAL)

The **domain layer** contains the core intellectual property and must be completely isolated:

1. **NO Home Assistant imports** - Zero `homeassistant.*` imports allowed
2. **NO external service dependencies** - Only Python standard library and domain code
3. **Pure business logic** - If it models real-world heating behavior, it belongs here
4. **Interface-driven** - All external interactions via Abstract Base Classes (ABCs)
5. **Type hints required** - All functions and methods must have complete type annotations

### Infrastructure Layer Rules

The **infrastructure layer** bridges the domain to Home Assistant:

1. **Implements domain interfaces** - All adapters must implement ABCs from domain layer
2. **HA-specific code only** - All `homeassistant.*` imports belong here
3. **Thin adapters** - Minimal logic, just translation between HA and domain
4. **No business logic** - Delegate all decisions to domain layer

## 🧪 Test-Driven Development (TDD) Standard

All new features must be developed using TDD:

### Unit Testing Requirements

1. **Domain-first testing** - Write domain layer tests BEFORE implementation
2. **Mock external dependencies** - Use mocks for all infrastructure interactions
3. **Test against interfaces** - Unit tests should test against ABCs, not concrete implementations
4. **Centralized fixtures** - Use a centralized `fixtures.py` file for test data (DRY principle)
5. **High coverage** - Aim for >80% coverage of domain logic
6. **Fast tests** - Domain tests should run in milliseconds (no HA, no I/O)

### Logging Standards

1. **Method Entry/Exit Logging** - All public methods in the domain and application layers must log at `DEBUG` level on entry and exit.
2. **State Changes and Results** - Use `INFO` level ONLY for:
   - State changes of IHP devices (e.g., heating started/stopped, mode changed)
   - Results of calculations or significant business events (e.g., decision results, LHS calculations)
   - Actual actions being performed (e.g., setting temperature, triggering scheduler)
3. **Device Context in Logs** - Infrastructure layer logs that reference IHP devices must include the device's user-friendly name (from Home Assistant's `friendly_name` attribute) rather than the entity ID.
4. **Parameter/Return Value Logging** - Input parameters and return values should be logged at `DEBUG` level.
5. **Initialization Logging** - Component initialization, configuration retrieval, and data fetching should be logged at `INFO` level.

### Python Environment Standards

1. **ALWAYS use Poetry** - Never run `python`, `pytest`, `pip` commands directly. Always use `poetry run python`, `poetry run pytest`, `poetry install`, etc.
2. **No direct interpreter execution** - Commands like `python -m pytest` or `python script.py` are forbidden. Use `poetry run pytest` or `poetry run python script.py`.
3. **Package management via Poetry only** - Use `poetry add package` for dependencies, never `pip install`.

### Documentation Standards

1. **No unsolicited documentation** - Do NOT create markdown files to document changes, summarize work, or write reports UNLESS explicitly requested by the user.
2. **Code-level documentation required** - Docstrings and inline comments are mandatory and should be maintained.
3. **PR descriptions only** - Summaries of work belong in pull request descriptions or conversation responses, not in repository markdown files.

### Testing Structure

```python
tests/
├── unit/
│   ├── domain/          # Pure domain logic tests (no mocks needed for value objects)
│   │   ├── test_value_objects.py
│   │   ├── test_pilot_controller.py
│   │   └── test_domain_services.py
│   └── infrastructure/  # Adapter tests (with mocked HA)
│       ├── test_scheduler_reader.py
│       └── test_climate_commander.py
└── integration/         # End-to-end tests (optional, slower)
```

### Example: Testing with Interfaces

```python
# domain/interfaces/scheduler_reader.py
from abc import ABC, abstractmethod
from domain.value_objects import ScheduleEvent

class ISchedulerReader(ABC):
    @abstractmethod
    async def get_next_event(self) -> ScheduleEvent | None:
        """Read the next scheduled event."""
        pass

# tests/unit/domain/test_pilot_controller.py
from unittest.mock import Mock
from domain.interfaces.scheduler_reader import ISchedulerReader
from domain.entities.pilot_controller import PilotController

def test_pilot_decides_to_preheat():
    # GIVEN: Mock scheduler reader
    mock_scheduler = Mock(spec=ISchedulerReader)
    mock_scheduler.get_next_event.return_value = ScheduleEvent(...)
    
    # WHEN: Controller makes decision
    controller = PilotController(scheduler_reader=mock_scheduler)
    decision = controller.decide_action()
    
    # THEN: Should preheat
    assert decision.action_type == "start_heating"
```

## 🎯 Initial Implementation: Core Abstractions

### A. Value Objects (Immutable Data Carriers)

Use Python **dataclasses** with `frozen=True` for all value objects:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class EnvironmentState:
    """Current environmental conditions."""
    current_temp: float
    outdoor_temp: float
    humidity: float
    timestamp: datetime

@dataclass(frozen=True)
class ScheduleEvent:
    """A scheduled heating event."""
    target_time: datetime
    target_temp: float
    event_id: str

@dataclass(frozen=True)
class PredictionResult:
    """Result of heating prediction."""
    anticipated_start_time: datetime
    estimated_duration_minutes: float
    confidence_level: float
```

### B. The Pilot Controller (Aggregate Root)

```python
from domain.interfaces.scheduler_reader import ISchedulerReader
from domain.interfaces.model_storage import IModelStorage
from domain.interfaces.climate_commander import IClimateCommander
from domain.value_objects import EnvironmentState, HeatingDecision

class PilotController:
    """Coordinates heating decisions for a single VTherm."""
    
    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        model_storage: IModelStorage,
        climate_commander: IClimateCommander,
    ) -> None:
        self._scheduler = scheduler_reader
        self._storage = model_storage
        self._commander = climate_commander
    
    async def decide_heating_action(
        self, 
        environment: EnvironmentState
    ) -> HeatingDecision:
        """Decide whether to start/stop heating based on predictions."""
        # Pure business logic here - no HA dependencies
        pass
```

### C. Interface Contracts (ABCs)

Define clear contracts for all external interactions:

```python
# domain/interfaces/scheduler_reader.py
from abc import ABC, abstractmethod
from domain.value_objects import ScheduleEvent

class ISchedulerReader(ABC):
    """Contract for reading scheduled events."""
    
    @abstractmethod
    async def get_next_event(self) -> ScheduleEvent | None:
        """Read the next scheduled heating event."""
        pass

# domain/interfaces/model_storage.py
from abc import ABC, abstractmethod

class IModelStorage(ABC):
    """Contract for persisting learning data."""
    
    @abstractmethod
    async def save_learned_slope(self, slope: float) -> None:
        """Persist a learned heating slope."""
        pass
    
    @abstractmethod
    async def get_learned_slopes(self) -> list[float]:
        """Retrieve historical learned slopes."""
        pass

# domain/interfaces/climate_commander.py
from abc import ABC, abstractmethod

class IClimateCommander(ABC):
    """Contract for climate control actions."""
    
    @abstractmethod
    async def start_heating(self, target_temp: float) -> None:
        """Start heating to reach target temperature."""
        pass
    
    @abstractmethod
    async def stop_heating(self) -> None:
        """Stop heating."""
        pass
```

## 📝 Code Style & Quality Standards

### Type Hints

- **Always use type hints** for function parameters and return values
- Use `from __future__ import annotations` for forward references
- Use `typing` module types: `Optional`, `Union`, `Protocol`, etc.
- Use `None` instead of `Optional[T]` for Python 3.10+ (written as `T | None`)

### Documentation

- **Docstrings required** - For all public classes and methods
- **User-centric and Developer-centric Docs** - Maintain separate, clear documentation streams: one focused on the user experience (how to use IHP), and another detailed guide for developers (API, architecture, contribution guidelines).
- **No Markdown Reports in Repository** - Avoid generating new Markdown files for reports (e.g., test reports, analysis summaries) directly within the repository. Such reports should be communicated in the pull request comments or directly in the conversation.
- Use Google-style docstrings
- Include type information in docstrings only when it adds clarity
- Document business rules and assumptions

### Code Organization

- **Single Responsibility** - Each class/function does one thing
- **Prefer Refactoring** - Prioritize refactoring existing classes and methods over creating new ones to avoid code bloat and ensure consistency.
- **Small functions** - Prefer functions under 20 lines
- **Clear naming** - Use descriptive names (e.g., `calculate_preheat_duration` not `calc`)
- **No magic numbers** - Use named constants
- **DRY Principle** - Actively seek and eliminate code duplication, not just in test fixtures but across the entire codebase.

### Python Standards

- Follow **PEP 8** style guide
- Use **dataclasses** for simple data structures
- Prefer **composition over inheritance**
- Use **async/await** for I/O operations
- Avoid global state

## 🚫 Anti-Patterns to Avoid

1. ❌ **Tight coupling to Home Assistant**
   ```python
   # BAD: Domain logic mixed with HA
   def calculate_preheat(self, hass: HomeAssistant):
       vtherm_state = hass.states.get("climate.vtherm")
   ```
   
   ✅ **Good: Clean separation**
   ```python
   # GOOD: Domain receives value objects
   def calculate_preheat(self, environment: EnvironmentState):
       temp = environment.current_temp
   ```

2. ❌ **Business logic in infrastructure**
   ```python
   # BAD: Decision-making in adapter
   class HASchedulerAdapter:
       async def get_next_event(self):
           event = self.hass.states.get(...)
           if event.temp > 20:  # Business rule!
               return None
   ```
   
   ✅ **Good: Infrastructure only translates**
   ```python
   # GOOD: Adapter just translates
   class HASchedulerAdapter:
       async def get_next_event(self):
           state = self.hass.states.get(...)
           return ScheduleEvent(...)  # Just data translation
   ```

3. ❌ **Untestable code**
   ```python
   # BAD: Hard to test (direct HA dependency)
   def decide():
       state = hass.states.get("climate.vtherm")
       if state.temperature < 20:
           hass.services.call("climate", "turn_on")
   ```
   
   ✅ **Good: Testable with interfaces**
   ```python
   # GOOD: Easily mockable
   def decide(commander: IClimateCommander, temp: float):
       if temp < 20:
           await commander.start_heating()
   ```

## 🔄 Migration Strategy

For existing code that doesn't follow these patterns:

1. **Don't break existing functionality** - Refactor incrementally
2. **Add abstractions first** - Create interfaces before moving code
3. **Test-first** - Write tests for new abstractions before refactoring
4. **One layer at a time** - Extract domain logic, then infrastructure
5. **Keep both working** - New and old code can coexist during migration

## 📚 Summary Checklist for New Code

Before submitting any AI-generated code, verify:

- [ ] Domain layer has NO `homeassistant.*` imports
- [ ] All external interactions use ABCs (interfaces)
- [ ] Value objects are immutable (`@dataclass(frozen=True)`)
- [ ] All functions have complete type hints
- [ ] Unit tests exist and use mocks for dependencies
- [ ] Tests use centralized fixtures (DRY principle)
- [ ] Tests can run without Home Assistant installed
- [ ] Business logic is in domain, infrastructure is thin
- [ ] No hardcoded fallback values - prefer WARNING logs and user alerts
- [ ] Code follows PEP 8 and uses meaningful names
- [ ] Docstrings explain the "why", not just the "what"

## 🎓 Philosophy

> "The domain is our valuable intellectual property. It must be protected from infrastructure concerns, testable in isolation, and clear in its intent. When Home Assistant changes, our domain logic remains stable. When we change our domain logic, tests catch regressions immediately."

**Focus on defining clear boundaries and interfaces first.** The quality of abstractions determines the quality of the entire system.
