# Contributing to Intelligent Heating Pilot

Thank you for wanting to improve IHP! This guide helps you get started.

## Quick Start

1. **Set up the environment**:
   ```bash
   poetry install
   poetry run pytest              # Run tests
   poetry run pytest tests/features/  # Run BDD scenarios
   ```

2. **Know the structure**:
   - **Domain layer** (`custom_components/intelligent_heating_pilot/domain/`) - core heating logic, no Home Assistant imports
   - **Infrastructure** (`infrastructure/`) - adapts Home Assistant to domain
   - **Tests** (`tests/`) - unit tests (TDD) + BDD features

3. **Understand the workflow**:
   - Each feature is ONE pull request
   - Agents iterate on the same branch (no per-phase PRs)
   - Three human validation gates: design → implementation → quality
   - See [WORKFLOW_MODEL.md](../.github/WORKFLOW_MODEL.md)

## Key Standards (Quick Reference)

| Item | Link |
|------|------|
| **Code Style** | [CONTRIBUTOR_STANDARDS.md](../.github/CONTRIBUTOR_STANDARDS.md) |
| **Architecture** | [copilot-instructions.md](../.github/copilot-instructions.md) |
| **Testing** | [BDD_TESTING.md](./BDD_TESTING.md) |

## Types of Contributions

### 🏗️ Architecture & Design
- Propose changes via **Design Discussion** issue
- Get feedback from Software Architect
- Reference [copilot-instructions.md](../.github/copilot-instructions.md)

### ✅ Testing & QA
- Write BDD features (acceptance criteria)
- Write unit tests (domain logic)
- See [BDD_TESTING.md](./BDD_TESTING.md) for patterns

### 💻 Implementation
- Follow [CONTRIBUTOR_STANDARDS.md](../.github/CONTRIBUTOR_STANDARDS.md)
- Implement domain logic (pure Python)
- Implement adapters (Home Assistant integration)

### 📚 Documentation
- User guides: `docs/`
- Developer guides: `.github/`
- Keep docs in sync with code

## Workflow Overview

1. **Design Phase** (Software Architect)
   - Analyze requirements
   - Design domain interfaces (ABCs)
   - Create BDD feature file

2. **Test Phase** (QA Engineer)
   - Write BDD step definitions
   - Write unit tests (RED phase)
   - All tests should FAIL initially

3. **Implementation Phase** (Developer)
   - Make tests PASS (GREEN phase)
   - Implement domain + infrastructure
   - Stay on same feature branch

4. **Review Phase** (Tech Lead)
   - Collaborative peer feedback
   - Optimize code, refactor
   - Merge when ready

See [WORKFLOW_MODEL.md](../.github/WORKFLOW_MODEL.md) for details.

## Testing Requirements

### BDD Features (Acceptance Criteria)
Location: `tests/features/*.feature`

```gherkin
Feature: Cache stores slope after heating
  Scenario: Temperature learning works
    Given a heating cycle is running
    When the cycle completes at 1.2°C/min
    Then cache stores the slope
```

### Unit Tests (TDD)
Location: `tests/unit/domain/` and `tests/unit/infrastructure/`

All domain tests should:
- FAIL before code is written
- PASS after code is written
- Use mocks for external dependencies

```python
def test_calculates_slope_from_temps():
    calculator = ContextualLHSCalculator()
    slope = calculator.calculate_slope([20.0, 21.5, 23.0])
    assert slope == pytest.approx(1.0)
```

## Logging

- **DEBUG**: Method entry/exit, parameters, return values
- **INFO**: State changes, business results (heating started, slope calculated)
- **WARNING**: Recoverable issues (missing sensor)
- **ERROR**: Unrecoverable failures

See [CONTRIBUTOR_STANDARDS.md](../.github/CONTRIBUTOR_STANDARDS.md#-logging) for examples.

## Questions?

- **Architecture**: See [copilot-instructions.md](../.github/copilot-instructions.md)
- **Testing**: See [BDD_TESTING.md](./BDD_TESTING.md)
- **Workflow**: See [WORKFLOW_MODEL.md](../.github/WORKFLOW_MODEL.md)
- **Code Style**: See [CONTRIBUTOR_STANDARDS.md](../.github/CONTRIBUTOR_STANDARDS.md)

---

**Happy contributing!** 🎯
