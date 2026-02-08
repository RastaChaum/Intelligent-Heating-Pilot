# Agent Workflow Orchestration - Intelligent Heating Pilot

## Overview

This workflow enforces DDD, SOLID, and TDD with explicit human validation gates.

## Workflow Diagram

```mermaid
flowchart TD
    Start([User Request]) --> Architect[Software Architect: Design + Skeletons]
    Architect --> Gate1{Human Validation}
    Gate1 -->|Approved| QA[QA Engineer: Tests RED]
    Gate1 -->|Changes| Architect

    QA --> Dev[Developer: Implementation GREEN]
    Dev --> Gate2{Human Validation}
    Gate2 -->|Approved| Lead[Tech Lead: Review/Refactor]
    Gate2 -->|Changes| QA

    Lead --> Docs[Documentation Agent]
    Docs --> End([Ready to Merge])

    style Architect fill:#ffb347
    style QA fill:#ff6b6b
    style Dev fill:#4ecdc4
    style Lead fill:#45b7d1
    style Docs fill:#6bcf7f
    style Gate1 fill:#ffd93d
    style Gate2 fill:#ffd93d
```

## Phase Details

### Phase 1: Software Architect (Design + Skeletons)
- Define domain model, interfaces, types, and class/method skeletons
- No implementation logic in method bodies
- Align with Home Assistant best practices
- Deliver acceptance criteria and test scenarios

### Phase 2: QA Engineer (TDD RED)
- Write unit tests for domain logic
- Write integration/E2E-minimum tests for cross-layer behavior
- Run tests with Poetry to confirm RED state

### Phase 3: Developer (TDD GREEN)
- Implement code to satisfy tests and contracts
- Keep domain pure and follow DDD boundaries
- Run tests with Poetry until green

### Phase 4: Tech Lead (Review/Refactor)
- Review for maintainability and SOLID compliance
- Refactor safely; keep tests green
- Coordinate with QA/Architect if changes are needed

### Phase 5: Documentation Agent
- Update user and contributor docs
- Keep documentation DRY and focused

## Human Validation Gates

- **Gate 1**: After Software Architect design
- **Gate 2**: After Developer implementation

No further phases proceed without approval.
