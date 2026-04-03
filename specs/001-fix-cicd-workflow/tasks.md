---
description: "Task list for feature 001-fix-cicd-workflow"
stage: task-generation
producer_agent: speckit.tasks
critical_reviewer_agent: speckit.analyze
implementation_producer_agent: speckit.implement
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Tasks: Fix CI/CD Workflow Enforcement

**Input**: Design documents from `/specs/001-fix-cicd-workflow/`
**Prerequisites**: spec.md ✅, plan.md ✅, quickstart.md ✅

**Tests**: No automated test framework applies to GitHub Actions YAML. Acceptance
criteria are verified manually via GitHub PR events (see quickstart.md). Algorithmic
bash logic (two-pass CHANGELOG diff, jq RC count expression) is tested via local
shell test scripts before and after the corresponding workflow edits.

**Organization**: Three independent user stories — one per workflow file — with no
shared foundational dependencies. All three phases can be implemented in parallel
after Phase 1 verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Confirm prerequisites are in place before editing the three workflow files.
No code is written in this phase.

- [ ] T001 Confirm `fetch-depth: 0` is present in the `Checkout` step of `.github/workflows/feature-fix-pr.yml` (required by the two-pass diff that calls `git show origin/integration:CHANGELOG.md`)

**Checkpoint**: Prerequisite verified — workflow editing can begin in all three phases in parallel.

---

## Phase 2: User Story 1 — Changelog Enforcement on Feature/Fix PRs (Priority: P1) 🎯 MVP

**Goal**: The `Check CHANGELOG update` step in `feature-fix-pr.yml` exits 1 when no
new non-blank line is added inside the `[Unreleased]` section relative to `origin/integration`.

**Independent Test**: Open a PR from a branch that does NOT modify `CHANGELOG.md`
targeting `integration` — the `validate-pr` check must appear as **failed** (not skipped).
See quickstart.md Scenarios 1 and 2.

### Tests for User Story 1 (MANDATORY) ⚠️

> Write and run tests BEFORE editing the workflow (TDD: confirm tests fail with existing code).

- [ ] T002 [P] [US1] Write `scripts/test-changelog-check.sh` — a self-contained bash test that locally exercises the two-pass diff logic from plan.md Decision 1 against five fixture scenarios: (a) no CHANGELOG.md change, (b) change only outside `[Unreleased]`, (c) valid addition inside `[Unreleased]`, (d) `[Unreleased]` section absent entirely, (e) only blank lines added inside `[Unreleased]`
- [ ] T003 [US1] Run `bash scripts/test-changelog-check.sh` before the workflow edit and confirm scenarios (a), (b), (d), (e) fail and scenario (c) passes — proving the test distinguishes correct from incorrect behavior

### Implementation for User Story 1

- [ ] T004 [US1] Replace the body of the `Check CHANGELOG update` step in `.github/workflows/feature-fix-pr.yml` with the two-pass diff implementation from plan.md Decision 1: extract `[Unreleased]` content from `HEAD` and from `origin/integration`, count new non-blank lines via `diff | grep '^>'`, and call `exit 1` with a human-readable message and the appropriate `Added`/`Fixed` suggestion template when `NEW_LINES -eq 0` (implements FR-001, FR-002, FR-006)
- [ ] T005 [US1] Update the `if:` condition on the `Suggest CHANGELOG template` step in `.github/workflows/feature-fix-pr.yml` from `steps.changelog-check.outputs.updated == 'false'` to `steps.changelog-check.outcome == 'failure'` so the PR comment is still posted when the new check step fails
- [ ] T006 [US1] Run `bash scripts/test-changelog-check.sh` again after the workflow edit and confirm all five scenarios now behave correctly — in particular that scenario (c) (valid `[Unreleased]` addition) exits 0 (happy-path passing test, SC-005)

**Checkpoint**: US1 complete — `feature-fix-pr.yml` enforces `[Unreleased]` content-level
check and exits 1 on violation. All test scenarios pass. ✅

---

## Phase 3: User Story 2 — Block Integration→Main Merge Without RC (Priority: P1)

**Goal**: `integration-pr.yml` produces a `failure` (not `skipped`) status when the source
branch is not `integration`, and also fails when no RC pre-release exists for the current version.

**Independent Test**: (a) Open a PR from `fix/issue-999` to `main` — first step must fail.
(b) Open a PR from `integration` to `main` with no RC tag — RC check step must fail.
See quickstart.md Scenarios 3 and 4.

### Tests for User Story 2 (MANDATORY) ⚠️

> Write and run tests BEFORE editing the workflow.

- [ ] T007 [P] [US2] Write `scripts/test-rc-check.sh` — a self-contained bash test that exercises the `jq` RC count expression (same pattern as plan.md Decision 3, applied to `integration-pr.yml`) against four mock `gh release list` JSON payloads: (a) empty list, (b) one dev pre-release only, (c) one RC pre-release, (d) multiple RCs
- [ ] T008 [US2] Run `bash scripts/test-rc-check.sh` before the workflow edit and confirm scenarios (a) and (b) evaluate to count=0 and scenarios (c) and (d) evaluate to count≥1

### Implementation for User Story 2

- [ ] T009 [US2] In `.github/workflows/integration-pr.yml`, atomically: (a) remove the job-level `if: github.head_ref == 'integration'` condition from `validate-integration-pr`, **and** (b) insert the `Enforce integration-only source branch` guard step as the **first** step of that job per plan.md Decision 2 — fail with `exit 1` when `github.head_ref != 'integration'` (implements FR-004, FR-006; both edits in one commit to avoid a transient broken state)
- [ ] T011 [US2] Add `exit 1` with a human-readable message to the `Check pre-release exists` step in `.github/workflows/integration-pr.yml` when `LATEST_RC` is empty, inside the `else` branch of the `LATEST_RC` check (implements FR-003, FR-006)
- [ ] T012 [US2] Run `bash scripts/test-rc-check.sh` again after the workflow edit and confirm all four mock scenarios evaluate correctly — in particular that scenarios (c) and (d) (RC pre-release present) evaluate to count≥1 (happy-path passing tests, SC-005)

**Checkpoint**: US2 complete — `integration-pr.yml` fails on invalid source branch and on
missing RC. Job-level `if:` replaced by explicit guard step. ✅

---

## Phase 4: User Story 3 — RC Existence Guard in Promotion Workflow (Priority: P2)

**Goal**: `promote-rc-to-release.yml` fails fast (before any artifact is created, modified,
or deleted) when no RC pre-release exists at merge time.

**Independent Test**: Code-review validation — confirm step order and fail-fast position.
See quickstart.md Scenario 5.

### Pre-Implementation Inspection for User Story 3

- [ ] T013 [P] [US3] Code-review validation: read `.github/workflows/promote-rc-to-release.yml` and confirm the following step order: `Extract version` → `Check if tag already exists` → *(new)* `Verify RC exists` → `Prepare release notes`; also confirm no step between `Verify RC exists` and `Prepare release notes` has `if: always()` that could bypass the failure

### Implementation for User Story 3

- [ ] T014 [US3] Insert the `Verify RC exists` step into `.github/workflows/promote-rc-to-release.yml` immediately after `Check if tag already exists` and before `Prepare release notes`, per plan.md Decision 3: query GitHub Releases API with `jq` for RC count, call `exit 1` with a human-readable three-line message when count=0 (implements FR-005, FR-006)

**Checkpoint**: US3 complete — `promote-rc-to-release.yml` fails immediately when no RC
exists; no release, CHANGELOG PR, or cleanup steps execute on failure. ✅

---

## Final Phase: Integration Validation & Review

**Purpose**: Cross-file consistency, syntax validation, and final review gate before merge.

- [ ] T015 [P] Lint all three modified workflow YAML files with `actionlint` or `yamllint` locally to catch syntax errors introduced during editing
- [ ] T016 [P] Cross-read all three workflows and verify consistent patterns: same version extraction path (`custom_components/intelligent_heating_pilot/manifest.json`), same `jq` RC filter style, same `gh release list` flag usage as the unmodified workflows
- [ ] T017 Perform final manual validation per quickstart.md Scenarios 1–4 against real GitHub PR events (or code-review Scenario 5 for promote workflow)
- [ ] T018 Update `specs/001-fix-cicd-workflow/spec.md` and `specs/001-fix-cicd-workflow/plan.md` front matter `review_status` from `pending` to `complete` after final review passes
- [ ] T020 Verify that `validate-pr` and `validate-integration-pr` are registered as required status checks in GitHub Settings → Branches → Branch protection rules (on `integration` and `main` respectively), ensuring guard-step failures produce `failure` conclusion (not `skipped`) as mandated by SC-002

---

## Phase N: Critical Review & Validation

**Reviewer**: `speckit.review` (different from `speckit.implement` — constitution WR-001)

- [ ] T019 Critical review: verify the three modified YAML files implement exactly what FR-001 through FR-008 require — no more, no less — and that no existing passing step was accidentally broken (SC-005); explicitly confirm each user story's happy-path scenario (CHANGELOG entry present → US1 passes; `integration` source branch → US2 passes; RC exists → US3 passes)

---

## Dependencies

```
T001
  ├── T002 (P, US1) ──► T003 ──► T004 ──► T005 ──► T006
  ├── T007 (P, US2) ──► T008 ──► T009 ─────────────► T011 ──► T012
  └── T013 (P, US3) ──────────────────────────────► T014

T006 ─┐
T012 ─┼──► T015 (P) ──┐
T014 ─┘                ├──► T017 ──► T018 ──► T019
                T016 ──┘
```

Phases 2, 3, and 4 are **fully independent** (different files) and can be started
in parallel after T001 completes.

## Parallel Execution Examples

**Per user story** (all start after T001):
```
Stream A (US1): T002 → T003 → T004 → T005 → T006
Stream B (US2): T007 → T008 → T009 → T011 → T012
Stream C (US3): T013 → T014
```

**Within a stream**: test scripts (T002, T007) can be written simultaneously.

## Implementation Strategy

**MVP scope**: US1 alone (T001–T006) delivers immediate value — every future PR
will be checked for CHANGELOG content. US2 and US3 can follow in any order.

**Recommended order**: US1 → US2 → US3 (decreasing frequency of the guarded operation).

**Total tasks**: 19
**Tasks per story**: US1 = 5, US2 = 5, US3 = 2, Final = 6, Phase N = 1
**Parallelizable tasks**: T002, T007, T013, T015, T016
