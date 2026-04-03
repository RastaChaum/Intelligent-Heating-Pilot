# Workflow Model

This repository uses the speckit workflow on a single feature branch from specification through review.

## Overview

1. `speckit.specify` creates or refines the specification.
2. `speckit.clarify` challenges gaps in the specification.
3. `speckit.plan` produces the implementation plan.
4. `speckit.checklist` reviews plan completeness.
5. `speckit.tasks` generates ordered execution tasks.
6. `speckit.analyze` checks cross-artifact consistency.
7. `speckit.implement` executes the work on the same branch.
8. `speckit.review` performs the critical implementation review.
9. `speckit.docs` updates documentation when the change impacts users, contributors, or maintainers.

## Branching Rule

- Feature branches must follow the naming format: `NNN-description`, `NNNN-description`, or `YYYYMMDD-HHMMSS-description` (e.g. `001-add-scheduler`, `20260319-143022-fix-slope`). The speckit tooling enforces this pattern.
- Keep the same feature branch for the full workflow.
- Do not create one pull request per stage.
- Refine artifacts and implementation on the same branch when review feedback arrives.

## Review Gates

### Specification and Plan

- Clarify the scope before planning.
- Tighten boundaries when the design is underspecified.

### Tasks and Coverage

- Add missing regression coverage before implementation starts.
- Keep task ordering explicit when dependencies exist.

### Implementation

- Fix boundary violations on the same branch.
- Re-run the relevant tests before asking for final review.

## Commit Guidance

Use clear prefixes to reflect the nature of the change:

```text
design: architecture or interface changes
test: test additions or coverage work
feat: new functionality
fix: bug fix
refactor: non-behavioral restructuring
docs: documentation changes
```

## Related Documentation

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [DEVELOPMENT_STANDARDS.md](./DEVELOPMENT_STANDARDS.md)
- [../../.github/agents/README.md](../../.github/agents/README.md)
- [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md)
