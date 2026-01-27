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

## 🌳 Git Branching Strategy

The project uses a **3-level branching strategy** to ensure code quality and stability:

```
main (production) ← integration (pre-release) ← feature/* (development)
```

### Branch Overview

#### 1. `main` - Production (Stable Releases)

**Role**: Contains only **tested and validated** production-ready code.

**Characteristics**:
- ✅ RELEASE versions only (v0.3.0, v0.4.0, etc.)
- ✅ Stable, tested, and documented code
- ✅ Protected: **no direct development**
- ✅ Fed only by PRs from `integration`
- ✅ Full history preserved (merge commits)

**Rules**:
- 🚫 **Forbidden**: Direct pushes, direct commits
- ✅ **Allowed**: Merge from `integration` via PR (after admin approval)
- ✅ **Merge strategy**: **Merge commit** (preserves full history)

#### 2. `integration` - Pre-Release (Aggregation)

**Role**: **Integration and pre-release** branch where all new features and fixes converge.

**Characteristics**:
- ✅ Receives PRs from `feature/*` branches
- ✅ Allows testing multiple features together
- ✅ Used to create **pre-releases** (v0.4.0-beta.1, etc.)
- ✅ Condensed history (squash merge of features)
- ✅ Protected: requires PRs for features

**Rules**:
- 🚫 **Forbidden**: Direct feature development
- ✅ **Allowed**: 
  - Merge from `feature/*` via PR with **squash merge**
  - Direct push by admin/contributors (minor fixes only)
- ✅ **Merge strategy**: **Squash merge** (one commit per feature)

#### 3. `feature/*` - Development (Individual Features)

**Role**: **Temporary** branches for developing new features or bug fixes.

**Characteristics**:
- ✅ One branch per feature/bug (e.g., `feature/issue-23-power-correlation`)
- ✅ Always created **from `main`**
- ✅ No protection (development freedom)
- ✅ Automatically deleted after merge
- ✅ Multiple commits OK during development

**Rules**:
- ✅ **Naming convention**: `feature/issue-XX-description` or `fix/issue-XX-description`
- ✅ **Base**: Always create from up-to-date `main`
- ✅ **Target**: Open PR to `integration` only
- ✅ **Merge strategy**: **Squash merge** (condenses all commits into one)

### Complete Workflow

#### Step 1: Create a Feature Branch

```bash
# 1. Update main
git checkout main
git pull origin main

# 2. Create feature branch from main
git checkout -b feature/issue-23-description

# 3. Push branch to GitHub
git push -u origin feature/issue-23-description
```

**Naming conventions**:
- `feature/issue-XX-short-description` - New feature
- `fix/issue-XX-short-description` - Bug fix
- `docs/update-readme` - Documentation change
- `refactor/domain-services` - Technical refactoring

#### Step 2: Develop with Regular Commits

```bash
# Make atomic commits during development
git add custom_components/intelligent_heating_pilot/domain/services/new_service.py
git commit -m "feat(domain): add NewService"

git add tests/unit/domain/test_new_service.py
git commit -m "test(domain): add unit tests for NewService"

# Push regularly
git push origin feature/issue-23-description
```

**Best practices**:
- Atomic commits (one logical change = one commit)
- Clear, descriptive messages
- Follow [Conventional Commits](https://www.conventionalcommits.org/) format
- Push regularly to avoid losing work

#### Step 3: Open Pull Request to `integration`

1. Go to GitHub repository
2. Click **Pull requests** → **New pull request**
3. **Base**: `integration` ← **Compare**: `feature/issue-23-description`
4. Fill out the PR template with:
   - Clear description of changes
   - Reference to related issues (`Fixes #23`)
   - Testing performed
   - Architecture compliance checklist
5. Wait for review and address feedback

#### Step 4: Squash Merge to `integration`

When the PR is approved:

1. Click **Squash and merge** 🎯
2. **Edit the squashed commit message** to summarize all changes:

```
feat: implement power correlation for slope filtering (#23)

- Add PowerHistoryTracker domain service
- Enrich SlopeData with power metadata
- Implement retrospective correlation algorithm
- Add comprehensive unit tests (>80% coverage)
- Update documentation

Closes #23
```

3. Confirm merge
4. Feature branch is **automatically deleted**

**Result**: In `integration`, you'll have **one clean commit** summarizing the entire feature.

#### Step 5: Create Pre-Release (Optional)

Before merging to `main`, test `integration` with a pre-release:

```bash
# 1. Switch to integration
git checkout integration
git pull origin integration

# 2. Tag pre-release
git tag v0.4.0-beta.1 -m "Pre-release v0.4.0-beta.1"

# 3. Push tag
git push origin v0.4.0-beta.1
```

GitHub Actions will automatically create the pre-release.

#### Step 6: Release to `main`

When `integration` is stable and tested:

1. Open PR from `integration` to `main`
2. Fill out release PR template
3. Admin reviews and approves
4. **Merge commit** to preserve full history
5. Tag release: `git tag v0.4.0 -m "Release v0.4.0"`
6. Push tag: `git push origin v0.4.0`

### Quick Summary for Contributors

1. **Always branch from `main`**: `git checkout main && git pull && git checkout -b feature/issue-XX-description`
2. **Target `integration`** for all feature/bug PRs
3. **Squash merge** into `integration` (one commit per feature)
4. **Only admins merge** `integration` → `main` (for releases)

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

- Python 3.13 or higher
- Poetry (for dependency management)
- Git
- (Recommended) VSCode with recommended extensions

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

4. **Set up pre-commit hooks (REQUIRED)**:
   ```bash
   poetry run pre-commit install
   ```
   
   This will automatically run code quality checks before each commit, preventing syntax errors and style issues from being committed.

### Code Quality Tools Setup

#### Pre-commit Hooks

Pre-commit hooks are **mandatory** for all contributors. They automatically check your code before each commit to prevent syntax errors, style issues, and common mistakes.

**Installation:**
```bash
# Install pre-commit hooks (one-time setup)
poetry run pre-commit install

# Test the hooks on all files (optional)
poetry run pre-commit run --all-files
```

**What the hooks check:**
- ✅ **Python syntax validation** - Ensures no syntax errors
- ✅ **Ruff linting** - Code style and common issues
- ✅ **Ruff formatting** - Consistent code formatting
- ✅ **mypy type checking** - Type annotation validation
- ✅ **Security checks** - Common security vulnerabilities (bandit)
- ✅ **File hygiene** - Trailing whitespace, EOF newlines, etc.

**Bypassing hooks (NOT recommended):**
```bash
# Only use in exceptional cases
git commit --no-verify -m "message"
```

#### VSCode Configuration

The repository includes VSCode configuration files in `.vscode/`. When you open the project, VSCode will:

1. **Suggest recommended extensions** - Accept the prompt to install them
2. **Auto-format on save** - Using Ruff formatter
3. **Show linting errors** - Real-time feedback as you type
4. **Run type checking** - Mypy integration

**Recommended extensions (auto-suggested):**
- **Ruff** (`charliermarsh.ruff`) - Linter and formatter
- **Python** (`ms-python.python`) - Python language support
- **Pylance** (`ms-python.vscode-pylance`) - Advanced IntelliSense
- **Mypy** (`matangover.mypy`) - Type checking
- **Error Lens** (`usernamehw.errorlens`) - Inline error display

**Manual VSCode setup (if needed):**
1. Install the recommended extensions
2. Open Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`)
3. Select "Python: Select Interpreter"
4. Choose the Poetry virtual environment (`.venv/bin/python`)

**Key VSCode settings (already configured):**
```json
{
  "editor.formatOnSave": true,           // Auto-format with Ruff
  "ruff.lint.run": "onSave",            // Run linter on save
  "python.linting.mypyEnabled": true,   // Enable mypy
  "files.trimTrailingWhitespace": true  // Remove trailing spaces
}
```

#### Manual Code Quality Checks

You can manually run code quality checks at any time:

```bash
# Check Python syntax (fast check)
find custom_components -name "*.py" -exec python -m py_compile {} +

# Run Ruff linter
poetry run ruff check custom_components/ tests/

# Auto-fix Ruff issues
poetry run ruff check --fix custom_components/ tests/

# Run Ruff formatter
poetry run ruff format custom_components/ tests/

# Run mypy type checker
poetry run mypy custom_components/intelligent_heating_pilot/

# Run all pre-commit hooks manually
poetry run pre-commit run --all-files

# Run security check
poetry run bandit -r custom_components/ -c pyproject.toml
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
- Line length: **100 characters** (Ruff formatter)
- Descriptive names (no obscure abbreviations)

### Ruff Configuration

The project uses Ruff for both linting and formatting:

```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["E203", "E501"]
```

**Selected rule categories:**
- `E` - pycodestyle errors
- `F` - Pyflakes (unused imports, undefined names, etc.)
- `I` - isort (import sorting)
- `UP` - pyupgrade (modern Python syntax)
- `B` - flake8-bugbear (common bugs)
- `SIM` - flake8-simplify (code simplification)

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

Use **Ruff** for formatting (replaces Black):

```bash
# Format code
poetry run ruff format custom_components/ tests/

# Check formatting without modifying
poetry run ruff format --check custom_components/ tests/
```

**Note:** Pre-commit hooks automatically format your code, so manual formatting is rarely needed.

### Type Checking

Use **mypy** for static type checking:

```bash
poetry run mypy custom_components/intelligent_heating_pilot/
```

## 🔄 Pull Request Process

### Before Submitting

**Pre-commit hooks will automatically check most of these, but verify:**

1. ✅ All tests pass locally: `poetry run pytest tests/unit/ -v`
2. ✅ Code formatted with Ruff (automatic via pre-commit)
3. ✅ No syntax errors (automatic via pre-commit)
4. ✅ No mypy errors (automatic via pre-commit)
5. ✅ No security issues (automatic via pre-commit)
6. ✅ Documentation updated if necessary
7. ✅ CHANGELOG.md updated (`[Unreleased]` section)

**Quick pre-submission check:**
```bash
# Run all quality checks manually
poetry run pre-commit run --all-files

# Run tests
poetry run pytest tests/unit/ -v
```

### GitHub Actions CI/CD

All pull requests automatically trigger GitHub Actions workflows that verify:

#### 🚀 CI Workflow (`.github/workflows/ci.yml`)

**Jobs:**
1. **Quick Syntax Check (Fast Fail)**
   - Runs first for immediate feedback
   - Checks Python syntax without installing dependencies
   - Fails fast if basic syntax errors exist

2. **Code Quality Checks**
   - Python syntax validation
   - Ruff linting
   - Ruff formatting check
   - mypy type checking

3. **Tests**
   - Runs unit tests
   - Generates coverage reports
   - Uploads coverage to Codecov (if configured)

**Workflow triggers:**
- Push to `main`, `integration`, `feature/**`, `fix/**` branches
- Pull requests to `main` or `integration`

**What to do if CI fails:**
1. Check the failed job in GitHub Actions tab
2. Read the error messages
3. Fix the issues locally
4. Run `poetry run pre-commit run --all-files` to verify
5. Commit and push the fixes

**Note:** Some checks are set to `continue-on-error: true` for now, but they should still be addressed.

### Release Workflow (`.github/workflows/create-release.yml`)

Automatically creates releases when version tags are pushed:

**Pre-release creation:**
```bash
# Tag a pre-release from integration branch
git checkout integration
git tag v0.5.0-beta.1 -m "Pre-release v0.5.0-beta.1"
git push origin v0.5.0-beta.1
```

**Release creation:**
```bash
# Tag a release from main branch
git checkout main
git tag v0.5.0 -m "Release v0.5.0"
git push origin v0.5.0
```

The workflow will:
- Create a GitHub release (pre-release for beta tags)
- Attach CHANGELOG.md and README.md
- Close referenced issues
- Update issue labels

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
