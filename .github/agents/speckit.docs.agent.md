---
description: Update user and contributor documentation impacted by a feature, fix, or release within the speckit workflow.
handoffs:
  - label: Final Review
    agent: speckit.review
    prompt: Re-check the updated documentation for consistency with the implementation and workflow artifacts
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Update documentation impacted by the current feature or fix while keeping the
documentation set concise, consistent, and easy to navigate.

## Responsibilities

1. Keep user-facing documentation accurate:
   - README.md
   - CHANGELOG.md
   - configuration, installation, usage, and troubleshooting docs
2. Keep contributor-facing documentation accurate when workflow, architecture, or
   project rules changed.
3. Remove outdated guidance instead of stacking duplicate explanations.
4. Keep all documentation in English with valid relative links.

## Standards

- Prefer updating existing documents over creating new markdown files.
- Do not create ad-hoc report files unless explicitly requested.
- Keep examples aligned with actual current behavior.
- Update version numbers and release notes only when the change requires it.
- If a feature changes user-visible behavior, documentation updates are mandatory.

## Execution Steps

1. Read spec.md, plan.md, tasks.md, and the relevant changed files.
2. Identify which documentation files are impacted.
3. Update only the necessary documents.
4. Ensure the result is DRY, consistent, and aligned with the constitution.
5. If documentation changed meaningfully, hand off to `speckit.review` for a final consistency check.
