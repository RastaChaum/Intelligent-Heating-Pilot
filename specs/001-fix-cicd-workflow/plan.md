---
stage: planning
producer_agent: speckit.plan
critical_reviewer_agent: speckit.checklist
review_status: in_review
---

# Implementation Plan: Fix CI/CD Workflow Enforcement

**Branch**: `001-fix-cicd-workflow` | **Date**: 2026-04-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-fix-cicd-workflow/spec.md`

## Summary

Three surgical fixes to existing GitHub Actions workflows that currently warn but
never block. The CHANGELOG check in `feature-fix-pr.yml` will compare the
`[Unreleased]` section between base and HEAD and call `exit 1` on no net addition.
`integration-pr.yml` will gain an explicit source-branch guard step (replacing the
job-level `if:` that produces `skipped`) and will call `exit 1` when no RC
pre-release exists. `promote-rc-to-release.yml` will gain a RC existence guard
step inserted before any artifact is created or modified.

No new files are created. No Python code is modified. Changes total ≈ 30–40 YAML
lines across three files.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow syntax), Bash (GNU coreutils, awk, diff, git, jq, GitHub CLI `gh`)
**Primary Dependencies**: `actions/checkout@v6`, `gh` CLI (pre-installed on `ubuntu-latest` runners), `jq` (pre-installed), standard POSIX utilities
**Storage**: N/A
**Testing**: Manual validation against real GitHub PR events; no automated test framework applicable to workflow YAML
**Target Platform**: GitHub Actions `ubuntu-latest` runners
**Project Type**: CI/CD workflow configuration
**Performance Goals**: N/A
**Constraints**: Changes confined to three existing YAML files; zero new files; no regression on currently passing scenarios
**Scale/Scope**: 3 files, ≈30–40 lines changed total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Home Assistant compliance gate**: N/A — no HA code involved
- [x] **Hexagonal DDD gate**: N/A — no domain layer; workflows contain no business logic
- [x] **Immutable domain gate**: N/A — no domain value objects
- [x] **Typed OOP gate**: N/A — no Python code
- [x] **Stateless service gate**: N/A — shell steps are inherently stateless
- [x] **Cohesive integration gate**: N/A — no cross-service communication
- [x] **Test strategy gate**: Acceptance is manual (PR event simulation on GitHub). No automated test framework applies to workflow YAML. BDD scenarios in spec define observable outcomes; no duplication of effort.
- [x] **Logging gate**: N/A — `echo` statements in shell steps serve as workflow logs; no IHP device names involved
- [x] **Poetry gate**: N/A — no Python execution in this feature; existing Poetry steps in the workflows are unchanged
- [x] **Agent review gate**: ✅ Producer: `speckit.plan`; reviewer: `speckit.checklist`
- [x] **Documentation gate**: ✅ No user/contributor docs required (self-documenting via step names and error messages)

**Post-design re-check**: All gates hold. No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-cicd-workflow/
├── spec.md           ✅ complete
├── plan.md           ← this file
├── research.md       ← Phase 0 output (below)
├── data-model.md     N/A (no domain entities)
├── quickstart.md     ← Phase 1 output (below)
├── contracts/        N/A (no external API)
└── tasks.md          Phase 2 output (speckit.tasks — not created here)
```

### Source Files Modified (repository root)

```text
.github/workflows/
├── feature-fix-pr.yml          # Fix: content-level CHANGELOG check + exit 1
├── integration-pr.yml          # Fix: guard step + exit 1 on missing RC
└── promote-rc-to-release.yml   # Fix: new RC existence guard step (fail fast)
```

**Structure Decision**: Single-project, no new files. Three targeted edits to existing YAML.

## Complexity Tracking

No constitution violations to justify.

---

## Phase 0: Research

### Decision 1 — CHANGELOG content detection pipeline

**Decision**: Two-pass diff comparison of the `[Unreleased]` section between base (`origin/integration`) and HEAD.

**Rationale**: Using `git diff --unified=N -- CHANGELOG.md` and awk to find added lines within the section requires the `## [Unreleased]` header to appear in the diff hunk's context window. With default `--unified=3`, any edit more than 3 lines below the header escapes detection. A large `--unified` value is wasteful. The two-pass approach directly compares section content and is robust regardless of section size or diff context.

**Implementation**:
```bash
HEAD_UNRELEASED=$(awk '/## \[Unreleased\]/{flag=1;next} /^## \[/{flag=0} flag{print}' CHANGELOG.md \
  | grep -v '^[[:space:]]*$')
BASE_UNRELEASED=$(git show origin/integration:CHANGELOG.md \
  | awk '/## \[Unreleased\]/{flag=1;next} /^## \[/{flag=0} flag{print}' \
  | grep -v '^[[:space:]]*$')

NEW_LINES=$(diff <(echo "$BASE_UNRELEASED") <(echo "$HEAD_UNRELEASED") \
  | grep '^>' | wc -l)

if [ "$NEW_LINES" -eq 0 ]; then
  echo "❌ No new lines added to the [Unreleased] section of CHANGELOG.md"
  exit 1
fi
echo "✅ CHANGELOG [Unreleased] section updated ($NEW_LINES new line(s))"
```

**Edge cases handled**:
- `[Unreleased]` section absent in base (fresh repo): `BASE_UNRELEASED` = empty → any HEAD content counts as new ✅
- `[Unreleased]` section absent in HEAD: script fails → correct ✅
- CHANGELOG.md not in the PR diff at all: `HEAD_UNRELEASED` = `BASE_UNRELEASED` → `NEW_LINES=0` → exit 1 ✅
- Only whitespace/empty lines added: filtered by `grep -v '^[[:space:]]*$'` → exit 1 ✅

**Alternatives considered**:
- `git diff --unified=9999 -- CHANGELOG.md | awk ...` — works but downloads the full file diff; rejected as wasteful
- File-level diff (`--name-only`) — cannot distinguish edits within vs. outside `[Unreleased]`; already in use and shown insufficient

---

### Decision 2 — Source-branch guard in `integration-pr.yml`

**Decision**: Remove the job-level `if: github.head_ref == 'integration'` condition and replace it with an explicit first step that calls `exit 1` when the source branch is not `integration`.

**Rationale**: A job-level `if:` that evaluates to false produces a `skipped` conclusion. GitHub branch protection rules treat `skipped` as satisfied (not failed) unless configured with `required` + "do not allow skipping" — a fragile operational dependency. An `exit 1` in a step guarantees `failure` regardless of branch protection configuration.

**Implementation**: New first step in the `validate-integration-pr` job:
```yaml
- name: Enforce integration-only source branch
  run: |
    if [ "${{ github.head_ref }}" != "integration" ]; then
      echo "❌ Only the 'integration' branch may merge into 'main'."
      echo "Source branch detected: ${{ github.head_ref }}"
      exit 1
    fi
    echo "✅ Source branch is 'integration'"
```

The trigger `on: pull_request: branches: [main]` already scopes the workflow to PRs targeting `main`. This step only affects the behavior within that scope — no new workflow runs are triggered.

**Alternatives considered**:
- Separate job `enforce-integration-only` — creates an extra required check to maintain; rejected as over-engineering for a single guard
- Keep `if:` + add `skips-if-disabled` branch protection setting — operationally fragile and invisible to the codebase; rejected

---

### Decision 3 — RC existence guard position in `promote-rc-to-release.yml`

**Decision**: Insert a new step `Verify RC exists` after the existing `Check if tag already exists` step and before `Prepare release notes`.

**Rationale**: The spec (FR-005) requires fail fast — no subsequent steps execute. Positioning the guard before `Prepare release notes` means: no release notes built, no CHANGELOG PR opened, no pre-release cleanup, no final release created. This is the earliest viable position after the version is known (extracted by the preceding `Extract version from manifest.json` step).

**Implementation**:
```yaml
- name: Verify RC exists
  id: rc-check
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    VERSION="${{ steps.version.outputs.version }}"
    RC_COUNT=$(gh release list --json tagName,isPrerelease \
      | jq -r --arg v "$VERSION" \
          '[.[] | select(.isPrerelease and (.tagName | test("^v" + $v + "-rc[0-9]+$")))] | length')
    if [ "$RC_COUNT" -eq 0 ]; then
      echo "❌ No release candidate found for v${VERSION}."
      echo "A validated RC (vX.Y.Z-rcN) must exist before promoting to a final release."
      echo "Use the 'Prepare Release Candidate' or 'Increment RC Version' workflows first."
      exit 1
    fi
    echo "✅ Found ${RC_COUNT} RC(s) for v${VERSION} — proceeding with promotion"
```

**Alternatives considered**:
- Modify `Prepare release notes` to also check RC — conflates two responsibilities; rejected
- Insert after `Prepare release notes` — too late (release notes already built; later steps could be skipped conditionally but that's not fail-fast); rejected

---

## Phase 1: Design & Contracts

### data-model.md

**N/A** — this feature introduces no domain entities, value objects, or data structures. Workflow steps pass string variables (`VERSION`, `RC_COUNT`, etc.) entirely within shell scope.

### contracts/

**N/A** — this feature exposes no external interface. It only modifies the internal behavior of CI/CD workflows that consumers observe via GitHub PR check statuses.

### quickstart.md

See [quickstart.md](./quickstart.md) — describes how to validate the three workflow changes against real and simulated PR scenarios.

### Agent context update

```text
Technology added: GitHub Actions YAML workflow authoring, bash two-pass diff
comparison for CHANGELOG section detection, GitHub CLI (`gh`) release query patterns
```


## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [ ] Home Assistant compliance gate: design aligns with <https://developers.home-assistant.io/>
- [ ] Hexagonal DDD gate: domain logic has zero `homeassistant.*` imports and uses explicit interfaces
- [ ] Immutable domain gate: domain value objects are immutable and domain tests can run without Home Assistant
- [ ] Typed OOP gate: public interfaces, docstrings, and models are strongly typed and documented
- [ ] Stateless service gate: shared mutable process-wide state is absent or explicitly justified
- [ ] Cohesive integration gate: service boundaries and direct calls vs HA events are justified explicitly
- [ ] Test strategy gate: BDD scenarios and technical validation match the feature's real risks
- [ ] Logging gate: DEBUG/INFO obligations and user-facing device naming are identified
- [ ] Poetry gate: commands, tooling, and examples use Poetry for Python execution
- [ ] Agent review gate: the plan names a producer agent and a different critical reviewer agent
- [ ] Documentation gate: user and contributor docs are identified, concise, easy to navigate, and English-only

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ----------------------------------- |
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
