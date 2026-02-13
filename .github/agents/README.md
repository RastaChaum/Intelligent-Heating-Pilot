# GitHub Copilot Agents - Intelligent Heating Pilot

## Overview

This directory contains specialized GitHub Copilot agents that orchestrate development using DDD, SOLID, and TDD.

## ⚡ Critical: Agent Invocation Method

**Always invoke agents using DIRECT MENTIONS** in Copilot chat:

```markdown
✅ CORRECT - Use direct mention:
@software-architect

Your delegation message here

❌ DON'T - Use indirect tool calls or runSubagent
```

**Why it matters**: Direct agent mentions guarantee each agent receives its own full tool set:
- `@software-architect` → gets design + file creation tools
- `@qa-engineer` → gets test + file creation tools
- `@developer` → gets implementation + git tools
- `@tech-lead` → gets review + git merge tools
- `@documentation-agent` → gets file + documentation tools

If an agent reports missing tools, it was likely invoked indirectly. Re-invoke with a direct `@agent-name` mention.

## Available Agents

### 0. Project Manager (`project_manager.agent.md`)
**Role**: Orchestrates the full workflow with human validation gates.
**Invoke**: `@project-manager`

### 1. Software Architect (`software_architect.agent.md`)
**Role**: Designs the solution, defines interfaces, types, and skeletons (no method logic).
**Invoke**: `@software-architect`

### 2. QA Engineer (`qa_engineer.agent.md`)
**Role**: Writes BDD feature files and unit tests first (TDD + BDD, RED phase).
**Invoke**: `@qa-engineer`

### 3. Developer (`developer.agent.md`)
**Role**: Implements code to make tests pass (TDD GREEN).
**Invoke**: `@developer`

### 4. Tech Lead (`tech_lead.agent.md`)
**Role**: Orchestrates peer feedback with Architect/QA, then reviews, refactors, and validates.
**Invoke**: `@tech-lead`

### 5. Documentation Agent (`documentation_agent.agent.md`)
**Role**: Updates user and contributor documentation.
**Invoke**: `@documentation-agent`

## Workflow

```
Feature/Bug Request
  ? [Create branch: git checkout -b feature/issue-XXX]
  ↓
Software Architect (design + DDD/SOLID skeletons, commit to feature/issue-XXX)
  ? [GATE: User reviews design]
  ↓ (iterate if feedback)
QA Engineer (BDD features + unit tests RED, commit to feature/issue-XXX)
  ? [GATE: User reviews test coverage]
  ↓ (iterate if feedback)
Developer (implementation GREEN, commit to feature/issue-XXX)
  ? [GATE: User validates functionality]
  ↓ (iterate if bugs)
Tech Lead (peer feedback with Architect/QA, refactor if needed, merge to main/integration)
  ↓
Documentation Agent (update CHANGELOG, docs)
  ↓
COMPLETE ✅
```

**KEY**: One PR per feature. All agents commit to the same branch. Iterate at each gate if needed.
See [WORKFLOW_MODEL.md](../WORKFLOW_MODEL.md) for detailed explanation.

## Recommended Entry Point

Use **Project Manager** to orchestrate the workflow end-to-end:

```markdown
@project-manager

Implement Issue #45: Pre-heating starts too early in humid weather.
```

## Documentation Index

**Quick Start**:
1. **[WORKFLOW_MODEL.md](../WORKFLOW_MODEL.md)** ← Start here (explains one-PR-per-feature model)
2. **[AGENT_TOOLS_MATRIX.md](../AGENT_TOOLS_MATRIX.md)** — Which tools each agent has (git/code/test/merge)

**For Each Role**:
3. **[CONTRIBUTOR_STANDARDS.md](../CONTRIBUTOR_STANDARDS.md)** — Development standards, code examples, conventions (maintained by Software Architect)
4. **[BDD_SETUP_GUIDE.md](../BDD_SETUP_GUIDE.md)** — pytest-bdd and Gherkin feature setup (QA Engineer reference)
5. **[PEER_REVIEW_GUIDELINES.md](../PEER_REVIEW_GUIDELINES.md)** — Collaborative feedback process (Tech Lead orchestrates)

**Architecture & Constraints**:
6. **[copilot-instructions.md](../copilot-instructions.md)** — DDD, SOLID, and core architectural principles
