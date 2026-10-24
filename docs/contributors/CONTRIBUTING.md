# Contributing to Intelligent Heating Pilot

Thank you for wanting to improve IHP. This guide helps you start contributing without digging through internal workflow files first.

## Quick Start

1. Set up the environment.

   ```bash
   poetry install
   poetry run pytest
   poetry run pytest tests/features/
   ```

2. Learn the project structure.

   - Domain layer: `custom_components/intelligent_heating_pilot/domain/`
   - Application layer: `custom_components/intelligent_heating_pilot/application/`
   - Infrastructure layer: `custom_components/intelligent_heating_pilot/infrastructure/`
   - Tests: `tests/`

3. Read the core references.

   - [architecture/OVERVIEW.md](../architecture/OVERVIEW.md)
   - [BDD_TESTING.md](./BDD_TESTING.md)
   - [DEVELOPMENT_STANDARDS.md](./DEVELOPMENT_STANDARDS.md)
   - [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md)

## Key References

| Topic | Document |
| --- | --- |
| Code style and repo rules | [DEVELOPMENT_STANDARDS.md](./DEVELOPMENT_STANDARDS.md) |
| Architecture | [architecture/OVERVIEW.md](../architecture/OVERVIEW.md) |
| Testing | [BDD_TESTING.md](./BDD_TESTING.md) |
| Release and maintenance | [maintainers/RELEASE_PROCESS.md](../maintainers/RELEASE_PROCESS.md) |

## Contribution Types

### Architecture and Design

- Propose boundary or model changes before implementation.
- Keep domain logic independent from Home Assistant.
- Use [architecture/OVERVIEW.md](../architecture/OVERVIEW.md) as the contributor entry point.

### Testing and QA

- Write BDD scenarios for observable behavior.
- Write unit tests for edge cases, validation, and error handling.
- Add regression coverage for every production bug that reveals a missing test.

### Implementation

- Follow the DDD boundaries and type-hint requirements.
- Keep adapters thin and business logic in domain services.
- Use Poetry for all Python commands.

### Documentation

- Keep user and contributor documentation in `docs/`.
- Keep GitHub configuration, agent definitions, and workflow files in `.github/`.
- Update the relevant permanent docs when behavior changes.

## Documentation Layout Policy

- The repository root should stay limited to standard GitHub entry files such as `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- Do not add architecture drafts, delivery summaries, audit reports, or versioned release-note markdown files at the repository root.
- Put architecture documentation in `docs/architecture/`.
- Put maintainer procedures in `docs/maintainers/`.

## Workflow Overview

1. Specify and refine the change scope.
2. Plan the design and test coverage.
3. Implement on the same feature branch.
4. Update documentation when the change affects users, contributors, or maintainers.
5. Run final review before merge.

See [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md) for the full speckit workflow.

## Testing Expectations

### BDD

- Store feature files under `tests/features/`.
- Use pytest-bdd step definitions for business-facing scenarios.

### Unit Tests

- Store domain tests under `tests/unit/domain/`.
- Store infrastructure tests under `tests/unit/infrastructure/`.
- Prefer mocks at external boundaries only.

## Logging

- `DEBUG`: method entry and exit, parameters, return values, initialization
- `INFO`: business events and device actions
- `WARNING`: recoverable problems
- `ERROR`: unrecoverable failures

See [DEVELOPMENT_STANDARDS.md](./DEVELOPMENT_STANDARDS.md) for the complete quick reference.

## Questions

- Architecture: [architecture/OVERVIEW.md](../architecture/OVERVIEW.md)
- Testing: [BDD_TESTING.md](./BDD_TESTING.md)
- Workflow: [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md)
- Documentation map: [README.md](../README.md)
