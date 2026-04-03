<!--
Sync Impact Report
- Version change: 1.0.0 -> 1.1.0
- Modified principles:
	- I. Home Assistant Development Guide Compliance -> I. Home Assistant Platform Compliance
	- II. Hexagonal Domain-Driven Architecture -> II. Hexagonal Domain-Driven Boundaries
	- III. Strongly Typed Object-Oriented Python -> III. Typed, Object-Oriented, Mostly Stateless Python
	- IV. SOLID Microservices with Event-Driven Decoupling -> IV. Cohesive Services and Explicit Integration Boundaries
	- V. Test-First Quality with TDD and BDD -> V. Test-First Quality with BDD and Technical Validation
- Added principles:
	- VI. Agent-Driven Workflow with Critical Peer Review
- Added sections:
	- Operational Standards and Documentation
- Removed sections:
	- None
- Templates requiring updates:
	- ✅ updated: .specify/templates/plan-template.md
	- ✅ updated: .specify/templates/spec-template.md
	- ✅ updated: .specify/templates/tasks-template.md
	- ✅ updated: .github/agents/speckit.specify.agent.md
	- ✅ updated: .github/agents/speckit.plan.agent.md
	- ✅ updated: .github/agents/speckit.tasks.agent.md
	- ✅ updated: .github/agents/speckit.implement.agent.md
	- ✅ updated: .github/agents/speckit.analyze.agent.md
	- ⚠ pending check: .specify/templates/commands/*.md (directory missing in repository)
- Deferred TODOs:
	- None
-->

# Intelligent Heating Pilot Constitution

## Core Principles

### I. Home Assistant Platform Compliance

Every change MUST comply with the Home Assistant developer guide and integration
quality expectations. Any divergence from platform conventions MUST be treated as
a defect and corrected before merge. Feature delivery MUST use a dedicated branch
and MUST not bypass repository review gates before merge.
Rationale: Platform consistency improves reliability, maintainability, and user trust.

### II. Hexagonal Domain-Driven Boundaries

The solution MUST follow hexagonal architecture with strict Domain-Driven Design
boundaries. The domain layer MUST contain zero `homeassistant.*` imports and MUST
depend only on the Python standard library plus domain code. All external
interactions MUST pass through explicit interfaces or abstract base classes, and
infrastructure MUST translate Home Assistant state into domain models without
embedding business rules. Domain value objects MUST be immutable.
Rationale: Clear boundaries protect business logic from framework churn.

### III. Typed, Object-Oriented, Mostly Stateless Python

Code MUST be written in object-oriented Python with explicit type hints for all
public methods, constructors, and return values. Public classes and methods MUST
have Google-style docstrings. Services and application coordinators SHOULD remain
stateless by default; shared mutable process-wide state is prohibited unless an
explicit repository, cache, or infrastructure boundary justifies it. Functions
SHOULD stay within 80 lines; longer functions MUST be justified by cohesion that
cannot be improved through simple extraction.
Rationale: Strong typing improves static validation and design clarity.

### IV. Cohesive Services and Explicit Integration Boundaries

Responsibilities MUST be split into small, cohesive services aligned with SOLID
principles and dependency inversion. Cross-service coordination MUST use explicit
orchestration seams, clear contracts, and Home Assistant events where asynchronous
decoupling materially improves isolation or extensibility. Direct calls are
acceptable only when they preserve architectural boundaries and remain simpler
than an event-driven alternative.
Rationale: Clear integration rules prevent accidental coupling without forcing
ceremony where it adds no value.

### V. Test-First Quality with BDD and Technical Validation

Test-first delivery is mandatory. Each feature MUST include BDD scenarios in
Gherkin for user-observable outcomes and technical tests for robustness whenever
boundary conditions, failure paths, or algorithmic behavior are relevant to the
change. Implementation MUST follow red-green-refactor, and the chosen test mix
MUST be explainable from the feature's actual risks rather than copied by habit.
Rationale: Tests must prove user value and technical resilience without creating
ritual or redundant work.

### VI. Agent-Driven Workflow with Critical Peer Review

Every lifecycle stage MUST be executed by a named agent and reviewed by a different
named agent before the workflow advances. The reviewer MUST challenge assumptions,
ambiguities, constitution compliance, testability, and traceability to the prior
stage. Self-approval is prohibited. Review findings MUST be resolved or explicitly
accepted before the next stage begins.
Rationale: Separate production and critique improves quality and reduces blind spots.

## Operational Standards and Documentation

Python commands and package management in workflow execution MUST use Poetry.
Logging MUST follow these rules:

- DEBUG for method entry and exit, parameters, return values, and initialization;
- INFO for state changes, significant business events, and actions taken;
- infrastructure logs referring to IHP devices MUST use the user-facing `friendly_name`
  rather than entity identifiers when available.

Documentation MUST be concise, consistent, easy to navigate, and split by audience:

- user documentation explains installation, configuration, usage, and troubleshooting;
- contributor documentation explains architecture, code conventions, and project rules.
Unsolicited markdown reports and duplicated guidance are prohibited. All
documentation and code artifacts MUST be in English.

## Delivery Workflow and Quality Gates

The standard workflow is constitution update when needed, then specification,
planning, task generation, implementation, and final validation. Each stage MUST:

- identify a producer agent and a different critical reviewer agent;
- record the review outcome before the next stage starts;
- preserve traceability to the previous stage;
- include explicit checks for Home Assistant compliance, DDD boundaries, typed OOP
  design, stateless service expectations, logging obligations, and documentation impact.

Every implementation task list MUST include tests before implementation for the
same scope and a final critical review task performed by an agent different from
the implementation agent.

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
- every review MUST block merge if a MUST rule is violated;
- every stage review MUST be performed by an agent different from the producing agent.

**Version**: 1.1.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-03
