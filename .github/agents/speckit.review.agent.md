---
description: Perform a critical post-implementation review of code, tests, and workflow artifacts before closure.
handoffs:
  - label: Return Findings For Fixes
    agent: speckit.implement
    prompt: Address the critical review findings and update the implementation without self-approval
    send: true
  - label: Update Documentation
    agent: speckit.docs
    prompt: Update the documentation impacted by the reviewed implementation and return for consistency review
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Review the completed implementation critically against the constitution, spec.md,
plan.md, tasks.md, changed code, and available test evidence. This agent is a
blocker gate, not a confirmation step.

## Review Posture

- Be critical rather than confirmatory: actively search for weak assumptions,
  missing tests, constitution violations, and traceability gaps.
- Do not self-approve work produced by the same agent.
- Findings MUST be prioritized by severity and tied to concrete files or workflow artifacts.

## Execution Steps

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks --validate-governance final` from repo root.
2. Read `spec.md`, `plan.md`, and `tasks.md` from the current feature directory.
3. Review changed code and tests against the declared requirements and constitution.
4. Verify that implementation evidence exists for:
   - Home Assistant compliance and DDD boundaries;
   - typed public interfaces and docstrings;
   - stateless service expectations or justified shared state;
   - BDD plus technical validation where relevant;
   - logging and documentation impact.
5. Review documentation impact explicitly:
  - verify README, CHANGELOG, configuration docs, or contributor docs were updated when needed;
  - flag outdated or duplicated documentation that should be removed.
6. Produce a findings-first review with blockers, risks, and only then a short summary.

## Output Format

1. Findings ordered by severity
2. Open questions or assumptions
3. Merge recommendation: blocked or ready

## Constraints

- Default to read-only review unless the user explicitly asks for remediation.
- If no findings are discovered, state that explicitly and mention residual risks.
