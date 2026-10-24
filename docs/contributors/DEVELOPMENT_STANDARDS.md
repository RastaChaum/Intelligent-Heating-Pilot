# Development Standards

This document is the quick-reference source of truth for day-to-day development standards.
For full architectural rules, see [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md).

## Core Engineering Rules

- Keep domain code free of `homeassistant.*` imports.
- Use complete type hints on all public functions and methods.
- Add Google-style docstrings to public classes and methods.
- Keep business logic in domain and translation logic in infrastructure.
- Use Poetry for all Python commands and dependency management.

## Documentation Layout

- User-facing and contributor-facing documentation belongs in `docs/`.
- The repository root should only contain standard GitHub entry documents such as `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, and `LICENSE`.
- Do not add ad-hoc reports, delivery summaries, implementation notes, or versioned release-note markdown files at the repository root.
- Put architecture references in `docs/architecture/` and maintainer procedures in `docs/maintainers/`.
- Summaries of completed work belong in pull requests, GitHub Releases, or chat responses, not in new repository markdown files.

## Logging

| Level | Use for |
| --- | --- |
| `DEBUG` | Method entry and exit, parameters, return values, initialization |
| `INFO` | Device state changes, business results, actions actually performed |
| `WARNING` | Recoverable problems and degraded behavior |
| `ERROR` | Unrecoverable failures |

Infrastructure logs that mention an IHP device must use the Home Assistant `friendly_name` instead of the raw entity ID.

## Testing

- Use BDD for business-visible behavior.
- Use unit tests for edge cases, failures, and algorithmic logic.
- Add regression tests for every production bug that escaped existing coverage.
- Prefer centralized fixtures and fast domain tests.

## Pull Request Checklist

- Domain boundaries are respected.
- New or changed public APIs are typed and documented.
- Tests cover the modified behavior.
- Documentation is updated when user-visible or contributor-visible behavior changed.
- New markdown files were added only when they belong in the permanent docs structure.

## References

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md)
- [../architecture/OVERVIEW.md](../architecture/OVERVIEW.md)
- [../maintainers/RELEASE_PROCESS.md](../maintainers/RELEASE_PROCESS.md)
- [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md)
