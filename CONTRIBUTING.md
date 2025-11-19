# Contributing to Intelligent Heating Pilot

Thank you for your interest in contributing to Intelligent Heating Pilot! This document describes the processes and best practices for contributing to the project.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Project Architecture](#project-architecture)
- [Development Environment Setup](#development-environment-setup)
- [Testing](#testing)
- [Code Standards](#code-standards)
- [Pull Request Process](#pull-request-process)

## 🤝 Code of Conduct

We are committed to maintaining an open and welcoming community. We expect all contributors to:

- Be respectful and professional
- Accept constructive criticism
- Focus on what is best for the community
- Show empathy towards other community members

## 🚀 How to Contribute

### Reporting Bugs

If you find a bug, please:

1. Check that it hasn't already been reported in [Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
2. Create a new issue using the "Bug Report" template
3. Include as much detail as possible:
   - Home Assistant version
   - IHP version
   - Relevant logs
   - Steps to reproduce the issue

### Proposing New Features

To propose a new feature:

1. Check that it isn't already proposed in Issues
2. Create an issue using the "Feature Request" template
3. Clearly explain:
   - The problem it solves
   - How you envision it working
   - Why it's useful for users

### Submitting Pull Requests

1. Fork the repository
2. Create a branch for your feature (`git checkout -b feature/my-new-feature`)
3. Commit your changes (`git commit -m 'feat: add my new feature'`)
4. Push to the branch (`git push origin feature/my-new-feature`)
5. Open a Pull Request

## 🏗️ Project Architecture

Intelligent Heating Pilot follows **Domain-Driven Design (DDD)** principles with strict separation of concerns.

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

### Folder Structure

```
custom_components/intelligent_heating_pilot/
├── domain/              # Pure business logic (NO Home Assistant dependencies)
│   ├── value_objects/   # Immutable value objects
│   ├── entities/        # Domain entities and aggregates
│   ├── interfaces/      # Contracts (Abstract Base Classes)
│   └── services/        # Domain services
├── infrastructure/      # Home Assistant integration layer
│   ├── adapters/        # Interface implementations
│   └── repositories/    # Data persistence
└── application/         # Orchestration and use cases
```

### **CRITICAL** Architectural Rules

#### Domain Layer (domain/)

1. ❌ **ABSOLUTE PROHIBITION** of importing `homeassistant.*`
2. ✅ Only Python standard library and domain code
3. ✅ All external interactions via Abstract Base Classes (ABCs)
4. ✅ Complete type annotations required
5. ✅ Unit tests without Home Assistant required

#### Infrastructure Layer (infrastructure/)

1. ✅ Implements domain interfaces
2. ✅ Contains all Home Assistant-specific code
3. ✅ Thin adapters - no business logic
4. ✅ Delegates all decisions to domain layer

## 🛠️ Development Environment Setup

### Prerequisites

- Python 3.11 or higher
- Poetry (for dependency management)
- Git

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/RastaChaum/Intelligent-Heating-Pilot.git
   cd Intelligent-Heating-Pilot
   ```

2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Local Development Configuration

To test the integration in Home Assistant:

1. Create a symbolic link to your Home Assistant installation:
   ```bash
   ln -s $(pwd)/custom_components/intelligent_heating_pilot \
         /path/to/homeassistant/config/custom_components/
   ```

2. Restart Home Assistant

3. Enable debug logging in `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```

### Docker Development

The project includes a Docker Compose configuration for development:

```bash
# Start Home Assistant in Docker
docker compose up -d

# View logs
docker compose logs -f homeassistant

# Restart after modifications
docker compose restart homeassistant
```

## 🧪 Testing

### Philosophy: Test-Driven Development (TDD)

This project strictly follows **TDD**:

1. ✅ Write tests **BEFORE** implementation
2. ✅ Domain layer tests first
3. ✅ Mocks for all external dependencies
4. ✅ Fast tests (<1 second for unit tests)

### Test Structure

```
tests/
├── unit/
│   ├── domain/          # Pure business logic tests
│   │   ├── fixtures.py  # Centralized fixtures (DRY principle)
│   │   ├── test_value_objects.py
│   │   ├── test_prediction_service.py
│   │   └── test_lhs_calculation_service.py
│   └── infrastructure/  # Adapter tests (with HA mocks)
│       ├── test_scheduler_reader.py
│       └── test_climate_commander.py
└── integration/         # Integration tests (optional, slower)
```

### Running Tests

```bash
# All unit tests
poetry run pytest tests/unit/ -v

# Domain layer tests only
poetry run pytest tests/unit/domain/ -v

# Tests with coverage
poetry run pytest --cov=custom_components.intelligent_heating_pilot tests/

# Specific file tests
poetry run pytest tests/unit/domain/test_prediction_service.py -v
```

### Example Test with Interfaces

```python
from unittest.mock import Mock
from domain.interfaces.scheduler_reader import ISchedulerReader
from domain.services.prediction_service import PredictionService

def test_prediction_calculates_anticipation():
    # GIVEN: Mock scheduler reader
    mock_scheduler = Mock(spec=ISchedulerReader)
    mock_scheduler.get_next_timeslot.return_value = ScheduleTimeslot(...)
    
    # WHEN: Service makes a prediction
    service = PredictionService(scheduler_reader=mock_scheduler)
    result = service.calculate_anticipation(environment_state)
    
    # THEN: Result meets expectations
    assert result.anticipated_start_time is not None
    assert result.confidence_level > 0.5
```

### Coverage Requirements

- Domain layer: **>80%** coverage
- Infrastructure layer: **>60%** coverage (harder to test code)
- All new features must include tests

## 📝 Code Standards

### Python Style

- Follow **PEP 8**
- Use complete type annotations
- Line length: 88 characters (Black formatter)
- Descriptive names (no obscure abbreviations)

### Type Annotations

```python
from __future__ import annotations  # For circular references

def calculate_anticipation(
    environment: EnvironmentState,
    target_temp: float,
) -> PredictionResult | None:
    """Calculate the required anticipation time."""
    pass
```

### Docstrings

Use **Google Style** format:

```python
def calculate_preheat_duration(
    current_temp: float,
    target_temp: float,
    heating_slope: float,
) -> float:
    """Calculate the required preheat duration.
    
    Args:
        current_temp: Current temperature in °C
        target_temp: Target temperature in °C
        heating_slope: Heating slope in °C/h
    
    Returns:
        Duration in minutes
        
    Raises:
        ValueError: If heating slope is <= 0
    """
    if heating_slope <= 0:
        raise ValueError("Heating slope must be positive")
    
    delta_temp = target_temp - current_temp
    return (delta_temp / heating_slope) * 60
```

### Immutability with Dataclasses

All value objects must be immutable:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class EnvironmentState:
    """Current environmental state."""
    current_temp: float
    outdoor_temp: float
    humidity: float
    timestamp: datetime
```

### Automatic Formatting

Use **Black** for formatting:

```bash
poetry run black custom_components/ tests/
```

### Type Checking

Use **mypy** for static type checking:

```bash
poetry run mypy custom_components/intelligent_heating_pilot/
```

## 🔄 Pull Request Process

### Before Submitting

1. ✅ All tests pass locally
2. ✅ Code formatted with Black
3. ✅ No mypy errors
4. ✅ Documentation updated if necessary
5. ✅ CHANGELOG.md updated (`[Unreleased]` section)

### Commit Convention

Use **Conventional Commits**:

```
feat: add humidity-based anticipation calculation
fix: correct negative heating slope calculation
docs: update README with new features
test: add tests for PredictionService
refactor: extract calculation logic to dedicated service
chore: update Poetry dependencies
```

Commit types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `test`: Adding or modifying tests
- `refactor`: Refactoring without behavior change
- `chore`: Maintenance (dependencies, config, etc.)

### Pull Request Template

When creating a PR, fill out the template with:

- Clear description of changes
- Reference to related issues (`Fixes #123`)
- Tests performed
- Screenshots if relevant
- Verification checklist

### Code Review

All PRs require:

1. ✅ Approval from at least one maintainer
2. ✅ Passing CI/CD tests (if configured)
3. ✅ DDD architecture compliance
4. ✅ Up-to-date documentation

## 🎯 DDD Best Practices

### ❌ Anti-patterns to Avoid

1. **Coupling to Home Assistant in the domain**
   ```python
   # ❌ BAD
   def calculate_preheat(self, hass: HomeAssistant):
       vtherm_state = hass.states.get("climate.vtherm")
   ```
   
   ```python
   # ✅ GOOD
   def calculate_preheat(self, environment: EnvironmentState):
       temp = environment.current_temp
   ```

2. **Business logic in infrastructure**
   ```python
   # ❌ BAD (business rule in adapter)
   class HASchedulerAdapter:
       async def get_next_event(self):
           event = self.hass.states.get(...)
           if event.temp > 20:  # Business rule!
               return None
   ```
   
   ```python
   # ✅ GOOD (adapter only translates)
   class HASchedulerAdapter:
       async def get_next_event(self):
           state = self.hass.states.get(...)
           return ScheduleEvent(...)  # Just translation
   ```

3. **Untestable code**
   ```python
   # ❌ BAD
   def decide():
       state = hass.states.get("climate.vtherm")
       if state.temperature < 20:
           hass.services.call("climate", "turn_on")
   ```
   
   ```python
   # ✅ GOOD
   async def decide(
       commander: IClimateCommander,
       temp: float
   ):
       if temp < 20:
           await commander.start_heating()
   ```

### ✅ Recommended Patterns

1. **Dependency injection via interfaces**
   ```python
   class HeatingPilot:
       def __init__(
           self,
           scheduler: ISchedulerReader,
           climate: IClimateCommander,
           storage: IModelStorage,
       ) -> None:
           self._scheduler = scheduler
           self._climate = climate
           self._storage = storage
   ```

2. **Immutable value objects**
   ```python
   @dataclass(frozen=True)
   class HeatingDecision:
       action: str
       target_temp: float
       reasoning: str
   ```

3. **Testing against interfaces**
   ```python
   def test_pilot_decides_to_heat():
       mock_scheduler = Mock(spec=ISchedulerReader)
       pilot = HeatingPilot(scheduler=mock_scheduler)
       decision = pilot.decide(environment)
       assert decision.action == "start_heating"
   ```

## 📚 Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed technical documentation
- [.github/copilot-instructions.md](.github/copilot-instructions.md) - AI instructions
- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Domain-Driven Design (DDD)](https://martinfowler.com/tags/domain%20driven%20design.html)
- [Test-Driven Development (TDD)](https://martinfowler.com/bliki/TestDrivenDevelopment.html)

## 🙏 Acknowledgements

Thank you for contributing to Intelligent Heating Pilot! Every contribution, whether it's a bug report, feature suggestion, or pull request, helps improve the project.

If you have questions, feel free to open a [Discussion](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions) or contact the maintainers.
