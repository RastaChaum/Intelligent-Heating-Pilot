# GitHub Copilot Agents - Intelligent Heating Pilot

## Overview

This directory now uses a speckit-only workflow. The old role-based agents are no
longer part of the supported process.

## Invocation

Use the speckit agent names directly in the local workflow tooling. Do not rely on
legacy `@role` mentions.

## Available Speckit Agents

- `speckit.constitution` — update governance rules when the workflow itself changes
- `speckit.specify` — produce the feature specification
- `speckit.clarify` — critically challenge the specification
- `speckit.plan` — produce the implementation and architecture plan
- `speckit.checklist` — critically challenge the plan and requirement quality
- `speckit.tasks` — generate the dependency-ordered task list
- `speckit.analyze` — critically review spec/plan/tasks consistency
- `speckit.implement` — execute the implementation plan
- `speckit.review` — perform the final critical review before closure
- `speckit.docs` — update impacted user and contributor documentation
- `speckit.taskstoissues` — convert tasks into GitHub issues when needed

## Standard Workflow

```text
Feature or bug request
  -> speckit.specify
  -> speckit.clarify
  -> speckit.plan
  -> speckit.checklist
  -> speckit.tasks
  -> speckit.analyze
  -> speckit.implement
  -> speckit.review
  -> speckit.docs (when documentation is impacted)
```

Each production stage is paired with a different critical reviewer. Governance
validation is enforced through YAML front matter plus `.specify/scripts/bash/validate-governance.sh`.

## Documentation Index

1. [../WORKFLOW_MODEL.md](../WORKFLOW_MODEL.md) — end-to-end speckit workflow
2. [../copilot-instructions.md](../copilot-instructions.md) — architectural and development constraints
3. [TESTING_STRATEGY.md](TESTING_STRATEGY.md) — BDD vs technical test decision framework
