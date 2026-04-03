---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: Fix CI/CD Workflow Enforcement

**Feature Branch**: `001-fix-cicd-workflow`
**Created**: 2026-04-03
**Status**: Draft
**Input**: User description: "Fix CI/CD workflow: enforce changelog check, restrict version bump to integration branch, block integration-to-main merge without RC"

## Context

The project follows a three-tier branching strategy:

- **feature/\* and fix/\*** — development branches (merged into `integration`)
- **integration** — staging branch where release candidates are prepared
- **main** — production branch, only receives final releases from `integration`

Three GitHub Actions workflows govern this flow:

| Workflow file | Trigger | Current gap |
|---|---|---|
| `feature-fix-pr.yml` | PR opened/updated targeting `integration` | CHANGELOG check posts a comment but never calls `exit 1`; PR can merge without a CHANGELOG entry |
| `integration-pr.yml` | PR opened/updated targeting `main` | Pre-release existence check warns but does not fail the workflow; PR can merge without a RC |
| `promote-rc-to-release.yml` | PR closed (merged) targeting `main` | Does not verify that a RC exists before creating the final release; can create a "0 RC" release |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Changelog Enforcement on Feature/Fix PRs (Priority: P1)

A developer opens a pull request from a `feature/*` or `fix/*` branch into `integration`.
The CI must refuse to let the PR merge if `CHANGELOG.md` has not been updated with at
least one entry in the `[Unreleased]` section relative to the base branch.

**Why this priority**: This is the most frequent operation in the workflow (every feature and fix).
Without enforcement, the CHANGELOG drifts and release preparation becomes time-consuming.

**Independent Test**: Can be fully tested by opening a PR from a `feature/*` branch that does
NOT modify `CHANGELOG.md` and verifying the workflow job ends with a non-zero exit code.

**Acceptance Scenarios**:

1. **Given** a PR from a `feature/*` branch into `integration`, **When** `CHANGELOG.md` has not been modified, **Then** the workflow job fails with a clear error message and the PR check is marked as failed.
2. **Given** a PR from a `feature/*` branch into `integration`, **When** `CHANGELOG.md` has been modified with an entry under `[Unreleased]`, **Then** the workflow job succeeds.
3. **Given** a PR from a `fix/*` branch into `integration`, **When** `CHANGELOG.md` has not been modified, **Then** the workflow job fails and suggests the `Fixed` section template.

---

### User Story 2 — Block Integration→Main Merge Without RC (Priority: P1)

A team member opens a pull request from `integration` into `main`.
The CI must refuse to let the PR merge if no GitHub pre-release matching
`vX.Y.Z-rcN` exists for the current version declared in `manifest.json`.

**Why this priority**: Merging to `main` without a validated RC bypasses the entire RC
validation cycle and can push untested code directly to HACS users.

**Independent Test**: Can be fully tested by triggering the `integration-pr.yml` check against
a state where no RC release exists on GitHub and verifying the job exits with a non-zero status.

**Acceptance Scenarios**:

1. **Given** a PR from `integration` into `main`, **When** no GitHub pre-release with tag `vX.Y.Z-rcN` exists for the current version, **Then** the workflow job fails explicitly, stating that a release candidate must be created first.
2. **Given** a PR from `integration` into `main`, **When** at least one RC pre-release exists for the current version, **Then** the pre-release check passes and the workflow continues.
3. **Given** a PR from a branch **other than** `integration` into `main`, **When** the PR is created, **Then** the workflow fails immediately, stating that only `integration` can merge into `main`.

---

### User Story 3 — RC Existence Guard in Promotion Workflow (Priority: P2)

The `promote-rc-to-release.yml` workflow runs when the `integration`→`main` PR is merged.
It must verify that at least one RC exists before creating the final GitHub release.
If no RC is found, the workflow must fail rather than silently creating an unvalidated release.

**Why this priority**: Safety net. Story 2 prevents the merge in most cases, but admin
force-merges can bypass branch protection. The promotion workflow is the last gate.

**Independent Test**: Can be tested by simulating a merge with no RC release in the GitHub
Releases API and verifying the workflow step exits with an error before any release is created.

**Acceptance Scenarios**:

1. **Given** an `integration`→`main` merge has occurred, **When** no RC tag exists for the current version, **Then** the promotion workflow fails immediately on the RC verification step, and does NOT create a GitHub release, does NOT open a CHANGELOG PR, and does NOT delete any pre-releases.
2. **Given** an `integration`→`main` merge has occurred, **When** at least one RC exists for the current version, **Then** the promotion workflow creates the final release and cleans up pre-releases.

---

### Edge Cases

- What if `CHANGELOG.md` is modified in the PR but only outside the `[Unreleased]` section (e.g., a past version's notes are edited)?
  → The check must extract added lines (`+` prefix) from the diff that fall strictly between the `## [Unreleased]` header and the next `## [` header. If no such lines exist, the check fails.
- What if no `[Unreleased]` section exists in `CHANGELOG.md`?
  → The check must fail with a message indicating the section is missing.
- What if the version in `manifest.json` on `integration` was not bumped relative to `main`?
  → The `integration-pr.yml` pre-release check still applies; no special case needed.
- What if the `copilot/feature/*` or `copilot/fix/*` prefix is used?
  → The existing branch naming regex already handles this; the CHANGELOG check must apply equally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `feature-fix-pr.yml` workflow MUST cause a CI failure (non-zero exit) when the diff of the PR branch against `origin/integration` does not include at least one added line (`+`) located within the `[Unreleased]` section of `CHANGELOG.md` (i.e., between the `## [Unreleased]` header and the next `## [` version header).
- **FR-002**: The failure message in FR-001 MUST include a suggested template for the appropriate change type (`Added` for features, `Fixed` for fixes).
- **FR-003**: The `integration-pr.yml` workflow MUST cause a CI failure (non-zero exit) when no GitHub pre-release matching the pattern `vX.Y.Z-rcN` exists for the version in `manifest.json`. The SC-002 guarantee (blocked 100% of the time) requires this check to be registered as a **required status check** in the `main` branch protection rules; this is an operational prerequisite documented in the Assumptions section.
- **FR-004**: The `integration-pr.yml` workflow MUST fail with a non-zero exit when the PR source branch is not `integration`. This MUST be implemented as an explicit guard step (not a job-level `if:` condition, which produces a `skipped` status that does not block merges). The workflow trigger (`on: pull_request: branches: [main]`) already restricts execution to PRs targeting `main`; FR-004 only concerns the source branch check within that scope.
- **FR-005**: The `promote-rc-to-release.yml` workflow MUST fail fast (non-zero exit on the RC verification step) if no RC pre-release exists for the current version. When this step fails, no subsequent steps SHALL execute — no GitHub release is created, no CHANGELOG PR is opened, and no pre-release cleanup is performed.
- **FR-006**: All failure steps MUST output a human-readable error message explaining what is missing and what action the contributor must take.
- **FR-007**: No existing passing scenarios must be broken; only missing `exit 1` guards need to be added.
- **FR-008**: No new workflow files are to be created; changes are confined to the three existing files: `feature-fix-pr.yml`, `integration-pr.yml`, and `promote-rc-to-release.yml`.

### Workflow Requirements *(mandatory)*

- **WR-001**: This specification is produced by `speckit.specify` and reviewed by `speckit.clarify`.
- **WR-002**: Planning is reviewed by `speckit.checklist`; task generation by `speckit.analyze`; implementation by `speckit.review`.
- **WR-003**: No unresolved clarification markers remain in this specification.

### Documentation Requirements *(mandatory)*

- **DR-001**: No new markdown documentation files are required; workflow YAML step names and error messages are self-documenting.
- **DR-002**: All workflow artifacts MUST remain in English.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A PR from a feature/fix branch that does not touch `CHANGELOG.md` is blocked by CI (check status = failed) 100% of the time.
- **SC-002**: A PR from `integration` to `main` is blocked by CI when no RC exists for the current version 100% of the time, provided the `validate-integration-pr` job is registered as a required status check in the `main` branch protection rules (see Assumptions).
- **SC-003**: A PR from any branch other than `integration` to `main` is blocked immediately with a clear error.
- **SC-004**: The `promote-rc-to-release.yml` workflow never creates a final GitHub release when no RC has been published.
- **SC-005**: All existing passing CI scenarios continue to pass after the fix (zero regressions).

## Clarifications

### Session 2026-04-03

- Q: At what level should the CHANGELOG check operate — file presence in the diff, or actual added content within the `[Unreleased]` section? → A: Content level — the diff must include at least one added line (`+`) within the `[Unreleased]` section (between `## [Unreleased]` and the next `## [` header).
- Q: When the RC verification fails in `promote-rc-to-release.yml`, should the job fail fast (no subsequent steps run) or skip only the destructive steps? → A: Fail fast — `exit 1` on the RC verification step; no subsequent steps execute (no release created, no CHANGELOG PR opened, no pre-release cleanup).
- Q: For SC-002 ("blocked 100% of the time"), is documenting branch protection as a required status check part of the spec scope? → A: Yes — the spec must explicitly state that the `validate-integration-pr` job and the `Check CHANGELOG update` step must be registered as required status checks in branch protection rules to provide the 100% blocking guarantee. — via the existing job-level `if:` condition (produces `skipped`, not `failure`) or via an explicit guard step? → A: Explicit guard step (`exit 1`) so the status is `failure` and blocks the merge. The `on: pull_request: branches: [main]` trigger already restricts the workflow to PRs targeting `main`; no scope change occurs.

## Assumptions

- The project relies on GitHub branch protection rules to enforce required status checks.
  Both the `Check CHANGELOG update` step in `feature-fix-pr.yml` and the `validate-integration-pr` job in `integration-pr.yml` MUST be registered as required status checks on their respective target branches (`integration` and `main`) for the 100% blocking guarantees in SC-001 and SC-002 to hold.
- `custom_components/intelligent_heating_pilot/manifest.json` is the single source of truth for
  the current version number.
- GitHub Releases (not git tags alone) are the authoritative source for RC existence, consistent
  with the approach already used across all existing workflows.
- `prepare-release-candidate.yml` and `increment-rc-version.yml` are already scoped to the
  `integration` branch via explicit checkout; no changes to these files are in scope.
