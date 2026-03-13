# Intelligent Heating Pilot — Claude Code Instructions

## Project Overview

Home Assistant custom integration for intelligent preheating using predictive algorithms and machine learning.
Repository: https://github.com/RastaChaum/Intelligent-Heating-Pilot

---

## Invoking Specialized Agent Roles

Claude does not use `@mentions`. To activate a specialized role, say:

> "Adopte le rôle de **[role]** défini dans `.github/agents/[file]` et..."

| Role | File | Responsibilities |
|------|------|-----------------|
| Project Manager | `project_manager.agent.md` | Orchestration, validation gates, delegation |
| Software Architect | `software_architect.agent.md` | DDD/SOLID design, interfaces, skeletons (no logic) |
| QA Engineer | `qa_engineer.agent.md` | BDD + TDD tests (RED phase) |
| Developer | `developer.agent.md` | Implementation to make tests GREEN |
| Tech Lead | `tech_lead.agent.md` | Code review, refactoring, merge validation |
| Documentation Agent | `documentation_agent.agent.md` | CHANGELOG, README, release notes |

**Typical entry point** — for a feature or bug fix:

```
Adopte le rôle de Project Manager défini dans .github/agents/project_manager.agent.md
et orchestre le développement de [feature/bug description].
```

---

## Development Workflow (One PR per feature)

```
Feature/Bug Request
  → [Branch: git checkout -b feature/issue-XXX]
  → Software Architect  (design + skeletons, commit "design: ...")
  → [GATE: user reviews design]
  → QA Engineer         (BDD + TDD tests RED, commit "test: ...")
  → [GATE: user reviews coverage]
  → Developer           (implementation GREEN, commit "feat/fix: ...")
  → [GATE: user validates behavior]
  → Tech Lead           (review, refactor, merge to integration/main)
  → Documentation Agent (CHANGELOG, docs update)
```

All agents commit to **the same feature branch**. No new PRs between phases.

---

## Architecture: Domain-Driven Design (CRITICAL)

```
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

**Non-redundancy rule**: if a happy path is covered by BDD, do NOT duplicate it as a unit test.

### Test Structure

```
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
- `CONTRIBUTOR_STANDARDS.md` is the single source of truth for dev standards
- Docstrings explain the "why", not just the "what"

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
- `.github/CONTRIBUTOR_STANDARDS.md` — team development standards
- `.github/WORKFLOW_MODEL.md` — detailed one-PR-per-feature model
- `ARCHITECTURE.md` — component architecture overview
