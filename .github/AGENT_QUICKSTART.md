# Quick Start: Agent-Driven Development

## Use the Project Manager

Invoke `@project-manager` and describe the feature or bug fix.

```markdown
@project-manager

Fix Issue #45: Pre-heating starts too early in humid weather.
```

The Project Manager will orchestrate:
1. Software Architect (design + code skeletons)
2. Human validation gate
3. QA Engineer (tests, RED)
4. Developer (implementation, GREEN)
5. Human validation gate
6. Tech Lead (review/refactor)
7. Documentation Agent (docs)

## Direct Invocation (Optional)

```markdown
@software-architect
Design interfaces, types, and skeleton classes for Issue #45.
```

```markdown
@qa-engineer
Write tests based on the approved design for Issue #45.
```

```markdown
@developer
Implement code to satisfy QA tests for Issue #45.
```

```markdown
@tech-lead
Review and refactor Issue #45 implementation.
```

```markdown
@documentation-agent
Update docs for Issue #45.
```

## Notes

- Tests must be run with Poetry: `poetry run pytest ...`
- Domain layer must remain free of Home Assistant imports
