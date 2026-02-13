# Workflow Model: One PR Per Feature (Iterative)

**TL;DR**: All agents commit to the SAME feature branch. No new PRs at each phase. Iterative refinement until done.

## Visual Workflow

```
Issue/Feature
  ↓
[Create branch: git checkout -b feature/issue-XXX]
  ↓
PHASE 1: SOFTWARE ARCHITECT
  ├─ Creates interfaces, value objects, skeletons
  ├─ Commits to feature/issue-XXX
  ├─ Pushes to GitHub
  └─ [GATE: User reviews design]
     If feedback → Architect refactors, commits more, pushes again
     If approved → Continue to Phase 2

PHASE 2: QA ENGINEER
  ├─ Creates BDD features + unit tests (RED)
  ├─ Commits to feature/issue-XXX
  ├─ Pushes to GitHub
  └─ [GATE: User reviews test coverage]
     If feedback → QA adds more tests, commits more, pushes again
     If approved → Continue to Phase 3

PHASE 3: DEVELOPER
  ├─ Implements code to pass tests (GREEN)
  ├─ Commits to feature/issue-XXX
  ├─ Pushes to GitHub
  └─ [GATE: User validates functionality]
     If bugs found → Developer fixes, commits more, pushes again
     If approved → Continue to Phase 4

PHASE 4: TECH LEAD
  ├─ Peer review with Architect/QA Engineer (via PR comments)
  ├─ Refactors if needed, commits
  ├─ Pushes to feature/issue-XXX
  └─ Merges feature/issue-XXX → main/integration
     (This closes the single PR)

PHASE 5: DOCUMENTATION AGENT
  └─ Updates CHANGELOG, docs
```

## Key Rules

### ✅ **DO**

- **Commit to the SAME branch** all phases
- **Push after each commit** (so PM can see progress)
- **If feedback received**: Refactor and commit more (don't create new PR)
- **Iterate until satisfied** at each gate before moving to next phase

### ❌ **DON'T**

- Don't create new PRs at each phase
- Don't create new branches (Architect design, QA tests, Developer impl, etc.)
- Don't use different commit strategies—be consistent
- Don't skip gates (user needs to validate before continuing)

## Example Flow (Iterative)

### Gate 1: Design Review

```
[User feedback]: "Can you move the temperature calculation to domain?"
[Architect action]: Refactor, git commit, git push
[User re-approval]: "Good, proceed to testing"
```

NO new PR created. Just more commits on the same branch.

### Gate 2: Test Coverage

```
[User feedback]: "Add tests for missing outdoor sensor"
[QA action]: Add scenario + unit test, git commit, git push
[User re-approval]: "Coverage looks good"
```

Again, same branch, more commits.

### Gate 3: Functionality

```
[User feedback]: "Heating doesn't start on cold days"
[Developer action]: Fix bug, git commit, git push, verify tests still GREEN
[User re-approval]: "Bug fixed, looks good"
```

Same branch, more commits.

### Merge (Tech Lead)

```
[Tech Lead]: Review all commits (Architect + QA + Developer + own refactors)
[Tech Lead]: Engage peers in PR comments
[Tech Lead]: Once satisfied, merge feature/issue-XXX → main
```

Single PR, now closed with merge.

## Commit Messages

Use conventional commits to keep history clear:

```
git commit -m "design: add IHeatingCycleCache interface"
git commit -m "design: fix domain layer purity in coordinator"
git commit -m "test(bdd): add heating cycle cache scenario"
git commit -m "test(unit): improve edge case coverage"
git commit -m "feat: implement heating cycle cache logic"
git commit -m "feat: fix heating start bug on cold days"
git commit -m "refactor(app): simplify coordinator orchestration"
```

## Benefits of This Model

| Aspect | Benefit |
|--------|---------|
| **Single PR** | Fewer GitHub notifications, cleaner history |
| **Iterative** | Design/test/implementation can be refined without new PRs |
| **Collaborative** | All peer feedback in one PR conversation |
| **Clear scope** | Branch name = issue, not agent action |
| **Simple** | Less overhead, easier to understand flow |

## Common Questions

**Q: What if the Architect made a huge mistake?**
A: They refactor and commit more to the same branch. The branch isn't closed until Tech Lead merges. User can always reject the entire branch if needed.

**Q: What if QA finds a huge hole in coverage?**
A: QA adds more tests, commits, pushes. No new PR. Developer then implements against the expanded test suite.

**Q: What if the branch gets out of sync with main?**
A: Rebase before merge (or merge main into feature first). Tech Lead handles this during finalization.

**Q: Can agents work in parallel (Architect + QA + Developer at same time)?**
A: Not on the same branch—merge conflicts. Workflow is sequential by design (ensures Quality gates).

---

**Reference**: See [Project Manager instructions](./agents/project_manager.agent.md) for detailed phase description.
