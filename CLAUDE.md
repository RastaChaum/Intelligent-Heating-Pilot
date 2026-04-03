# Intelligent Heating Pilot — Claude Code Instructions

## Project Overview

Home Assistant custom integration for intelligent preheating using predictive algorithms and machine learning.
Repository: <https://github.com/RastaChaum/Intelligent-Heating-Pilot>

---

## Invoking Speckit Agents

This repository now uses speckit workflow agents instead of legacy role-based agents.

| Speckit Agent | File | Responsibilities |
| ------------- | ---- | ---------------- |
| Specify | `speckit.specify.agent.md` | Write the feature specification |
| Clarify | `speckit.clarify.agent.md` | Critically challenge the specification |
| Plan | `speckit.plan.agent.md` | Produce the architecture and implementation plan |
| Checklist | `speckit.checklist.agent.md` | Critically challenge requirement and plan quality |
| Tasks | `speckit.tasks.agent.md` | Generate dependency-ordered execution tasks |
| Analyze | `speckit.analyze.agent.md` | Critically review spec, plan, and tasks consistency |
| Implement | `speckit.implement.agent.md` | Execute the implementation |
| Review | `speckit.review.agent.md` | Perform final critical review |
| Docs | `speckit.docs.agent.md` | Update impacted documentation |

**Typical entry point** — for a feature or bug fix:

```text
Use speckit.specify for the feature request, then follow the speckit workflow through
clarify, plan, checklist, tasks, analyze, implement, review, and docs when needed.
```

---

## Development Workflow (One PR per feature)

```text
Feature/Bug Request
    → speckit.specify
    → speckit.clarify
    → speckit.plan
    → speckit.checklist
    → speckit.tasks
    → speckit.analyze
    → speckit.implement
    → speckit.review
    → speckit.docs (if documentation is impacted)
```

All agents commit to **the same feature branch**. No new PRs between phases.

---

## Architecture: Domain-Driven Design (CRITICAL)

```text
custom_components/intelligent_heating_pilot/
├── domain/              # Pure business logic — ZERO homeassistant.* imports
│   ├── value_objects/   # @dataclass(frozen=True) immutable carriers
│   ├── entities/        # Aggregate roots, domain entities
│   ├── interfaces/      # ABCs (contracts for all external interactions)
│   └── services/        # Domain services
├── infrastructure/      # HA integration — implements domain interfaces
│   ├── adapters/        # Thin translators (HA API → domain value objects)
│   └── repositories/    # Data persistence
└── application/         # Orchestration / use cases
```

### Domain Layer Rules (non-negotiable)

- NO `homeassistant.*` imports — ever
- All external interactions via ABCs (interfaces)
- Value objects: `@dataclass(frozen=True)`
- Complete type hints on all functions/methods
- Google-style docstrings on all public classes/methods

### Infrastructure Rules

- Implements domain ABCs only
- Zero business logic — just HA↔domain translation
- All `homeassistant.*` imports confined here

---

## Testing Strategy (Hybrid BDD/TDD)

Full strategy: `.github/agents/TESTING_STRATEGY.md`

**Use pytest-bdd (Gherkin)** for:

- Business-observable behavior (happy paths, user scenarios)
- Features a Product Owner can understand

**Use pytest unit tests (TDD)** for:

- Edge cases (None, empty, overflow)
- Exception handling, error paths
- Algorithmic correctness

### Test Structure

```text
tests/
├── features/            # BDD: Gherkin .feature files + conftest.py step definitions
├── unit/
│   ├── domain/          # Pure domain logic (fixtures in domain/fixtures.py)
│   └── infrastructure/  # Adapter tests with mocked HA
└── integration/         # Cross-layer tests (optional, slower)
```

### Running Tests

```bash
# Always use Poetry — never python -m pytest or direct pytest
poetry run pytest tests/ -v
poetry run pytest tests/unit/ -v
poetry run pytest tests/features/ -v
```

---

## Python Environment (Strict)

- **Always use Poetry** — `poetry run pytest`, `poetry run python`, `poetry add`
- Never: `python -m pytest`, `pip install`, direct `pytest`

---

## Code Quality Standards

- **SOLID** — SRP, dependency inversion via interfaces
- **DRY** — centralized fixtures in `tests/unit/domain/fixtures.py`
- **Small functions** — prefer under 20 lines
- **No magic numbers** — named constants
- **Callee validates** — callers only check return values
- **Composition over inheritance**
- **async/await** for all I/O

### Logging Conventions

- `DEBUG`: method entry/exit, parameters, return values, initialization
- `INFO`: state changes, significant business events, actions taken
- Infrastructure logs: use device `friendly_name`, not entity ID

---

## Git Conventions

```bash
# Commit message prefixes
design: ...   # Software Architect (interfaces, skeletons)
test: ...     # QA Engineer (BDD features, unit tests)
feat: ...     # Developer (new feature implementation)
fix: ...      # Developer (bug fix)
refactor: ... # Tech Lead (non-behavior changes)
docs: ...     # Documentation Agent
```

---

## Documentation Rules

- **No unsolicited markdown reports** — summaries go in PR descriptions or conversation
- **No French in code or documentation** — all code artifacts in English
- `docs/contributors/DEVELOPMENT_STANDARDS.md` is the single source of truth for dev standards
- Docstrings explain the "why", not just the "what"
- User and contributor documentation belongs in `docs/`
- Architecture references belong in `docs/architecture/`; maintainer procedures belong in `docs/maintainers/`
- Do not commit non-standard documentation files at the repository root

---

## Anti-Patterns (Never Do)

```python
# BAD: HA dependency in domain
def calculate_preheat(self, hass: HomeAssistant): ...

# GOOD: domain receives value objects
def calculate_preheat(self, environment: EnvironmentState): ...

# BAD: business logic in adapter
class HASchedulerAdapter:
    async def get_next_event(self):
        if event.temp > 20:  # Business rule! Wrong layer
            return None

# GOOD: adapter just translates
class HASchedulerAdapter:
    async def get_next_event(self):
        state = self.hass.states.get(...)
        return ScheduleEvent(...)  # Data translation only
```

---

## Key Reference Files

- `.github/copilot-instructions.md` — full DDD/SOLID/TDD rules with examples
- `.github/agents/TESTING_STRATEGY.md` — BDD vs TDD decision guide
- `docs/contributors/DEVELOPMENT_STANDARDS.md` — team development standards
- `docs/contributors/WORKFLOW_MODEL.md` — detailed one-PR-per-feature model
- `ARCHITECTURE.md` — component architecture overview
