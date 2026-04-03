# BDD Testing Guide - pytest-bdd

This guide explains how to write and run BDD (Behavior-Driven Development) tests for IHP using **pytest-bdd** and **Gherkin**.

## What is BDD?

BDD bridges business requirements and code through **Gherkin feature files**—human-readable scenarios that become executable tests.

**Example**:
```gherkin
Feature: Cache stores slope after heating
  Scenario: Cache preserves learned slope across restarts
    Given a heating cycle has completed
    And the slope was 1.2 degrees per minute
    When the vTherm restarts
    Then the cached slope is still 1.2 degrees per minute
```

This file becomes a pytest test that developers and non-technical stakeholders can read.

---

## File Structure

```
tests/
├── features/
│   └── heating_cache.feature     # Gherkin scenarios (human-readable)
│   └── conftest.py               # Step definitions (code that implements scenarios)
└── unit/
    ├── domain/
    │   └── test_*.py             # Unit tests for domain logic (TDD)
    └── infrastructure/
        └── test_*.py             # Unit tests for adapters (TDD)
```

---

## 1. Writing Gherkin Features

### File: `tests/features/heating_cache.feature`

```gherkin
Feature: Heating Cycle Cache Management
  Caching improves efficiency by preserving learned heating slopes.

  Background:
    Given a heating system configured for climate.living_room

  Scenario: Cache stores LHS slope on cycle completion
    Given a heating cycle is running
    And LHS model is trained to 1.2°C/min
    When heating cycle completes
    Then cache stores slope 1.2°C/min
    And next heating uses cached slope

  Scenario: Cache persists after vTherm restart
    Given cache contains slope 1.5°C/min
    When vTherm is restarted
    Then cache slope is 1.5°C/min
```

### Gherkin Structure

| Keyword | Purpose | Example |
|---------|---------|---------|
| **Feature** | Describes capability | "Heating Cycle Cache Management" |
| **Background** | Setup common state | "Given a heating system..." |
| **Scenario** | One test case | "Cache stores slope on completion" |
| **Given** | Initial state | "a heating cycle is running" |
| **When** | Action | "heating cycle completes" |
| **Then** | Expected result | "cache stores slope" |
| **And** | Connect steps | "And next heating uses cache" |

---

## 2. Step Definitions (pytest-bdd)

### File: `tests/features/conftest.py`

```python
import pytest
from pytest_bdd import scenarios, given, when, then
from datetime import datetime
from unittest.mock import AsyncMock, Mock

# Load all *.feature files from this directory
scenarios('.')

# ============================================
# FIXTURES (Reusable test data)
# ============================================

@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = Mock()
    hass.data = {}
    return hass

@pytest.fixture
def cache_service():
    """Service under test."""
    from custom_components.intelligent_heating_pilot.domain.services.cache_service import CacheService
    return CacheService()

# ============================================
# GIVEN: Initial state
# ============================================

@given("a heating cycle is running")
def heating_cycle_running(mock_hass):
    """Set up a heating cycle in progress."""
    mock_hass.data['heating_active'] = True
    mock_hass.data['start_temp'] = 20.0
    mock_hass.data['current_temp'] = 20.0
    return mock_hass

@given("LHS model is trained to 1.2°C/min")
def lhs_trained(cache_service):
    """Set slope value."""
    cache_service.learned_slope = 1.2
    return cache_service

@given("cache contains slope 1.5°C/min")
def cache_has_slope(cache_service):
    """Initialize cache with slope."""
    cache_service.save_slope(1.5)

# ============================================
# WHEN: Actions
# ============================================

@when("heating cycle completes")
def complete_heating_cycle(mock_hass):
    """Simulate cycle completion."""
    mock_hass.data['heating_active'] = False
    mock_hass.data['end_temp'] = 22.4  # 1.2°C per minute × 2 minutes

@when("vTherm is restarted")
def restart_vtherm(mock_hass, cache_service):
    """Simulate vTherm restart."""
    cache_service.reload()

# ============================================
# THEN: Assertions
# ============================================

@then("cache stores slope 1.2°C/min")
def check_cache_slope(cache_service):
    """Verify slope was cached."""
    assert cache_service.get_slope() == pytest.approx(1.2)

@then("next heating uses cached slope")
def next_uses_cache(cache_service):
    """Verify cache is consulted for next cycle."""
    assert cache_service.was_used_in_last_calculation

@then("cache slope is 1.5°C/min")
def verify_cache_persisted(cache_service):
    """Verify cache survives restart."""
    assert cache_service.get_slope() == 1.5
```

---

## 3. Running Tests

### Run All BDD Features

```bash
# Run all *.feature scenarios
poetry run pytest tests/features/

# Run verbose (show each step)
poetry run pytest tests/features/ -v

# Run one feature file
poetry run pytest tests/features/heating_cache.feature

# Run one scenario
poetry run pytest tests/features/heating_cache.feature::test_cache_stores_lhs_slope_on_cycle_completion
```

### Output Example

```
tests/features/heating_cache.feature::test_cache_stores_lhs_slope_on_cycle_completion PASSED
  Given a heating cycle is running                                        PASSED
  And LHS model is trained to 1.2°C/min                                   PASSED
  When heating cycle completes                                            PASSED
  Then cache stores slope 1.2°C/min                                        PASSED
  And next heating uses cached slope                                      PASSED
```

---

## 4. Best Practices

### ✅ DO

- **One scenario, one behavior** - Each `Scenario` tests one thing
  ```gherkin
  Scenario: Cache stores slope after heating completes
    # Only tests caching, not restart
  ```

- **Use Background for common setup**
  ```gherkin
  Background:
    Given a heating system exists
    And climate entity is available
    # These run before each Scenario
  ```

- **Reuse fixtures** - Share mocks in `@pytest.fixture`
  ```python
  @pytest.fixture
  def cache_service():
      return CacheService()  # Used by all steps
  ```

- **Keep steps simple** - One assertion per `Then`
  ```python
  @then("cache stores slope")
  def check_cache(cache_service):
      assert cache_service.get_slope() is not None
  ```

### ❌ DON'T

- **Multiple behaviors in one Scenario**
  ```gherkin
  Scenario: Cache updates and persists to file and sends event
    # ❌ Three behaviors, should be three scenarios
  ```

- **Implementation details in Gherkin**
  ```gherkin
  Scenario: JSON file is updated
    # ❌ Too technical, should say "cache persists"
  ```

- **Hardcoded values in steps**
  ```python
  @then("slope is stored")
  def check(cache_service):
      assert cache_service.slope == 1.2  # ❌ Magic number
  ```

---

## 5. Parametrized Tests

Test multiple inputs with one scenario template:

```gherkin
Scenario Outline: Cache stores various slopes
  Given cache receives slope <slope>
  When I retrieve the slope
  Then slope should be <slope>

  Examples:
    | slope |
    | 0.5   |
    | 1.2   |
    | 2.0   |
```

Python:
```python
@given(parsers.parse("cache receives slope {slope:f}"))
def set_slope(cache_service, slope):
    cache_service.save_slope(slope)

@then(parsers.parse("slope should be {slope:f}"))
def check_slope(cache_service, slope):
    assert cache_service.get_slope() == pytest.approx(slope)
```

---

## 6. Debugging Tests

### Run with stdout
```bash
poetry run pytest tests/features/ -s
```

### Drop into debugger
```python
@then("cache stores slope")
def check_cache(cache_service):
    import pdb; pdb.set_trace()  # Breakpoint
    assert cache_service.get_slope() is not None
```

### Verbose output
```bash
poetry run pytest tests/features/ -vv --tb=short
```

---

## 7. Integration with TDD (Unit Tests)

**BDD** and **TDD** work together:

| Phase | BDD Feature | Unit Test | Code |
|-------|-------------|-----------|------|
| RED | Scenario written | Unit test FAILS | (not written) |
| GREEN | Scenario passing | Unit test PASSES | Implemented |
| REFACTOR | Scenario still passes | Tests still pass | Optimized |

**Example workflow**:

1. QA writes feature:
   ```gherkin
   Scenario: Cache stores slope
     When cycle completes
     Then cache has slope
   ```

2. QA writes unit tests (RED):
   ```python
   def test_save_slope():
       cache = CacheService()
       cache.save_slope(1.2)
       assert cache.get_slope() == 1.2  # FAILS (no code)
   ```

3. Developer implements (GREEN):
   ```python
   class CacheService:
       def __init__(self):
           self.slope = None

       def save_slope(self, value):
           self.slope = value  # Now test PASSES

       def get_slope(self):
           return self.slope
   ```

4. Feature test now PASSES (acceptance criteria met)

---

## 8. Fixtures & Mocking

### Centralized Test Data

**File: `tests/fixtures.py`** (DRY principle)

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_hass():
    """Reusable mock Home Assistant."""
    hass = Mock()
    hass.states = Mock()
    hass.services = AsyncMock()
    hass.data = {}
    return hass

@pytest.fixture
def environment_state():
    """Standard test environment."""
    from custom_components.intelligent_heating_pilot.domain.value_objects import EnvironmentState
    from datetime import datetime
    return EnvironmentState(
        current_temp=20.0,
        outdoor_temp=5.0,
        humidity=45.0,
        timestamp=datetime.now()
    )
```

Use in tests:
```python
def test_controller_decides(environment_state, mock_hass):
    controller = PilotController(mock_hass, environment_state)
    decision = controller.decide_action()
    assert decision is not None
```

---

## 9. Coverage

Check BDD + unit test coverage:

```bash
poetry run pytest tests/ --cov=custom_components/intelligent_heating_pilot/domain --cov-report=html
```

Open `htmlcov/index.html` to see coverage. Target: **>80% domain logic**.

---

## Summary

| Element | Purpose | Location |
|---------|---------|----------|
| **Feature file** | Business requirements in Gherkin | `tests/features/*.feature` |
| **Step definitions** | Gherkin → Python code | `tests/features/conftest.py` |
| **Unit tests** | TDD RED/GREEN cycles | `tests/unit/domain/`, `tests/unit/infrastructure/` |
| **Fixtures** | Shared test data | `tests/fixtures.py` |
| **Mocks** | Fake Home Assistant | `unittest.mock`, `pytest-asyncio` |

---

**For more on pytest-bdd**: https://pytest-bdd.readthedocs.io/
