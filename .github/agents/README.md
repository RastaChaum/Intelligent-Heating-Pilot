# GitHub Copilot Agents - Intelligent Heating Pilot

## Overview

This directory contains specialized GitHub Copilot agents that orchestrate development using DDD, SOLID, and TDD.

## Available Agents

### 0. Project Manager (`project_manager.agent.md`)
**Role**: Orchestrates the full workflow with human validation gates.
**Invoke**: `@project-manager`

### 1. Software Architect (`software_architect.agent.md`)
**Role**: Designs the solution, defines interfaces, types, and skeletons (no method logic).
**Invoke**: `@software-architect`

### 2. QA Engineer (`qa_engineer.agent.md`)
**Role**: Writes unit and integration tests first (TDD RED).
**Invoke**: `@qa-engineer`

### 3. Developer (`developer.agent.md`)
**Role**: Implements code to make tests pass (TDD GREEN).
**Invoke**: `@developer`

### 4. Tech Lead (`tech_lead.agent.md`)
**Role**: Reviews, refactors, and validates before documentation.
**Invoke**: `@tech-lead`

### 5. Documentation Agent (`documentation_agent.agent.md`)
**Role**: Updates user and contributor documentation.
**Invoke**: `@documentation-agent`

## Workflow

```
Feature/Bug Request
  -> Software Architect (design + code skeletons)
  -> Human validation gate
  -> QA Engineer (tests, RED)
  -> Developer (implementation, GREEN)
  -> Human validation gate
  -> Tech Lead (review/refactor)
  -> Documentation Agent (docs)
```

## Recommended Entry Point

Use **Project Manager** to orchestrate the workflow end-to-end:

```markdown
@project-manager

Implement Issue #45: Pre-heating starts too early in humid weather.
```

## Related Docs

- [AGENT_QUICKSTART.md](../AGENT_QUICKSTART.md)
- [AGENT_WORKFLOW.md](../AGENT_WORKFLOW.md)
- [copilot-instructions.md](../copilot-instructions.md)
