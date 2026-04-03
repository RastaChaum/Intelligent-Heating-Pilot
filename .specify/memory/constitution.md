<!--
Sync Impact Report
- Version change: N/A (template) -> 1.0.0
- Modified principles:
	- Template Principle 1 Name -> I. Home Assistant Development Guide Compliance
	- Template Principle 2 Name -> II. Hexagonal Domain-Driven Architecture
	- Template Principle 3 Name -> III. Strongly Typed Object-Oriented Python
	- Template Principle 4 Name -> IV. SOLID Microservices with Event-Driven Decoupling
	- Template Principle 5 Name -> V. Test-First Quality with TDD and BDD
- Added sections:
	- Documentation Strategy and Language Policy
	- Delivery Workflow and Quality Gates
- Removed sections:
	- None
- Templates requiring updates:
	- ✅ updated: .specify/templates/plan-template.md
	- ✅ updated: .specify/templates/spec-template.md
	- ✅ updated: .specify/templates/tasks-template.md
	- ✅ updated: .github/agents/speckit.tasks.agent.md
	- ⚠ pending check: .specify/templates/commands/*.md (directory missing in repository)
- Deferred TODOs:
	- None
-->

# Intelligent Heating Pilot Constitution

## Core Principles

### I. Home Assistant Development Guide Compliance
Every change MUST comply with the Home Assistant developer guide and integration
quality expectations. Any divergence from platform conventions MUST be treated as
a defect and corrected before merge.
Rationale: Platform consistency improves reliability, maintainability, and user trust.

### II. Hexagonal Domain-Driven Architecture
The solution MUST follow hexagonal architecture with strict Domain-Driven Design
boundaries. The domain layer MUST remain pure and independent from Home Assistant,
while adapters and infrastructure MUST translate between Home Assistant and domain
models through explicit interfaces.
Rationale: Clear boundaries protect business logic from framework churn.

### III. Strongly Typed Object-Oriented Python
Code MUST be written in object-oriented Python with explicit type hints for all
public methods, constructors, and return values. Data contracts MUST be modeled
with typed classes or dataclasses, and implicit typing in core business behavior
MUST be avoided.
Rationale: Strong typing improves static validation and design clarity.

### IV. SOLID Microservices with Event-Driven Decoupling
Responsibilities MUST be split into small, cohesive services aligned with SOLID
principles and dependency inversion. Service-to-service coordination MUST be
decoupled via Home Assistant event emission and subscription. Direct, tightly
coupled cross-service calls are prohibited except at explicit orchestration seams.
Rationale: Decoupled event flows reduce cascade failures and simplify evolution.

### V. Test-First Quality with TDD and BDD
Test-first delivery is mandatory. Each feature MUST include:
- unit tests that validate robustness, boundary conditions, and out-of-range inputs;
- BDD behavior tests in Gherkin that validate user-observable outcomes.
Implementation MUST follow red-green-refactor, and behavior coverage plus edge
coverage MUST both be demonstrable before completion.
Rationale: Dual-layer testing prevents regressions and confirms user value.

## Documentation Strategy and Language Policy

Documentation MUST be concise, non-duplicative, and split by audience:
- user documentation explains installation, configuration, usage, and troubleshooting;
- contributor documentation explains architecture, code conventions, and project rules.
All documentation and all code artifacts MUST be in English.

## Delivery Workflow and Quality Gates

Every planning artifact MUST include explicit checks for Home Assistant compliance,
DDD/hexagonal boundaries, typed OOP design, SOLID decomposition, and event-driven
integration. Every implementation task list MUST include unit and BDD test tasks,
with tests executed before implementation tasks for the same scope.

## Governance
This constitution is authoritative for specification, planning, tasks, and review.
Amendments MUST be documented in the constitution with a Sync Impact Report and
approved through repository review before use.

Versioning policy:
- MAJOR: incompatible governance changes or principle removals/redefinitions;
- MINOR: new principle/section or materially expanded mandatory guidance;
- PATCH: clarifications and wording improvements without semantic change.

Compliance review expectations:
- every plan MUST pass a Constitution Check before design completion;
- every task list MUST map work items to constitution requirements;
- every review MUST block merge if a MUST rule is violated.

**Version**: 1.0.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-03
