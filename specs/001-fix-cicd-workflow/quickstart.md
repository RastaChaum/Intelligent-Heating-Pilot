# Quickstart: Validating CI/CD Workflow Enforcement Changes

This guide explains how to verify the three workflow fixes work as intended.
No automated test framework applies to GitHub Actions YAML; validation is done
via real PR events or manual review against the scenarios defined in the spec.

## Prerequisites

- Write access to the repository (to open PRs and create releases)
- `gh` CLI authenticated locally
- The three changed files committed to a test branch

---

## Scenario 1 — CHANGELOG check blocks a PR without `[Unreleased]` content

**Target workflow**: `feature-fix-pr.yml`

1. Create a branch from `integration`: `git checkout -b test/no-changelog integration`
2. Make a trivial change (e.g., add a comment to any Python file)
3. Open a PR targeting `integration`
4. Observe the `validate-pr` job: the `Check CHANGELOG update` step must exit with code 1
5. The PR check must appear as **failed** (red ✗), not skipped

**Expected log output**:
```
❌ No new lines added to the [Unreleased] section of CHANGELOG.md
```

---

## Scenario 2 — CHANGELOG check passes after adding an `[Unreleased]` entry

1. On the same branch, add a line under `## [Unreleased]` in `CHANGELOG.md`
2. Push and observe the PR check: `Check CHANGELOG update` step exits 0
3. The remainder of the job (tests) must proceed normally

---

## Scenario 3 — Source-branch guard blocks non-integration PRs to `main`

**Target workflow**: `integration-pr.yml`

1. Open a PR from **any branch other than `integration`** targeting `main`
2. Observe the `validate-integration-pr` job: the first step `Enforce integration-only source branch` must exit 1
3. The PR check must appear as **failed** — no subsequent steps run

**Expected log output**:
```
❌ Only the 'integration' branch may merge into 'main'.
Source branch detected: <your-branch-name>
```

---

## Scenario 4 — RC check blocks an `integration`→`main` PR when no RC exists

**Target workflow**: `integration-pr.yml`

1. Ensure no GitHub pre-release matching `vX.Y.Z-rcN` exists for the current version:
   ```bash
   VERSION=$(jq -r '.version' custom_components/intelligent_heating_pilot/manifest.json)
   gh release list --json tagName,isPrerelease \
     | jq -r --arg v "$VERSION" '.[] | select(.isPrerelease and (.tagName | test("^v" + $v + "-rc[0-9]+$"))) | .tagName'
   # Expected: (empty)
   ```
2. Open a PR from `integration` targeting `main`
3. Observe the `validate-integration-pr` job: the `Check pre-release exists` step must exit 1
4. No Python setup or test steps must execute

**Expected log output**:
```
❌ No release candidate found for v<VERSION>.
```

---

## Scenario 5 — Promote workflow fails fast when no RC exists

**Target workflow**: `promote-rc-to-release.yml`

> ⚠️ This scenario requires triggering a merged PR event, which is destructive.
> Use a disposable test branch or verify via dry-run code review instead of
> executing on the real repository.

**Code review validation** (safe):
1. Read `promote-rc-to-release.yml`
2. Confirm the `Verify RC exists` step appears **before** `Prepare release notes`
3. Confirm it calls `exit 1` when `RC_COUNT -eq 0`
4. Confirm no subsequent step has `if: always()` that would bypass the failure

---

## Branch Protection Required Status Checks

After deploying the fixes, ensure the following checks are registered as
**required status checks** in GitHub Settings → Branches:

| Branch | Required check name |
|--------|-------------------|
| `integration` | `validate-pr` (from `feature-fix-pr.yml`) |
| `main` | `validate-integration-pr` (from `integration-pr.yml`) |

Without these registrations, the workflow failures do not block merges.
